"""Validate a bounded wheel snapshot, project through installer, compose owners.

Never extract, import wheel code, inspect the target filesystem, or resolve wheels.
"""
from __future__ import annotations

import base64
import configparser
import csv
import hashlib
import importlib.metadata
import io
import json
import os
import posixpath
import re
import stat
import struct
import zipfile
from collections import defaultdict
from email import policy
from email.parser import Parser
from pathlib import Path
from typing import Any

from installer import install
from installer.destinations import SchemeDictionaryDestination
from installer.records import Hash, RecordEntry
from installer.scripts import Script
from installer.sources import WheelFile
from installer.utils import parse_entrypoints
from packaging.tags import parse_tag
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version

PROFILE = "posix-case-sensitive-v1"
SCHEMES = frozenset({"purelib", "platlib", "scripts", "headers", "data"})
LIMITS = {
    "wheels": 64,
    "archive_bytes": 64 * 1024 * 1024,
    "member_bytes": 64 * 1024 * 1024,
    "metadata_bytes": 2 * 1024 * 1024,
    "wheel_uncompressed_bytes": 256 * 1024 * 1024,
    "set_uncompressed_bytes": 512 * 1024 * 1024,
    "set_archive_bytes": 256 * 1024 * 1024,
    "wheel_entries": 10000,
    "set_entries": 20000,
    "layout_bytes": 16384,
    "path_bytes": 4096,
    "path_depth": 64,
    "report_bytes": 16 * 1024 * 1024,
    "report_claim_references": 50000,
}
_IDENTIFIER = r"[A-Za-z_]\w*"
_OBJECT = re.compile(rf"{_IDENTIFIER}(?:\.{_IDENTIFIER})*\s*:\s*{_IDENTIFIER}(?:\.{_IDENTIFIER})*(?:\s*\[[A-Za-z0-9_. ,\-]*\])?\Z")
_NAME = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?\Z")


class InvalidInput(ValueError):
    """An unsupported or invalid input, never a clean audit."""


def _fail(message: str) -> None:
    raise InvalidInput(message)


def _safe_path(path: Any, *, absolute: bool = False, directory: bool = False) -> str:
    if not isinstance(path, str) or not path:
        _fail("path must be a nonempty string")
    if any(ord(c) < 32 or 127 <= ord(c) <= 159 or 0xD800 <= ord(c) <= 0xDFFF for c in path):
        _fail("control characters and surrogates in paths are unsupported")
    if "\\" in path or len(path.encode("utf-8")) > LIMITS["path_bytes"]:
        _fail("backslashes or overlong paths are unsupported")
    if absolute != path.startswith("/") or path.startswith("//"):
        _fail("expected an absolute POSIX path" if absolute else "expected a relative POSIX path")
    body = path[1:] if absolute else path
    if directory and body.endswith("/"):
        body = body[:-1]
    if absolute and not body:
        return path
    parts = body.split("/")
    if len(parts) > LIMITS["path_depth"] or any(p in ("", ".", "..") for p in parts):
        _fail("empty, dot, parent, or overly deep path components are unsupported")
    if any(len(p.encode("utf-8")) > 255 for p in parts):
        _fail("path component exceeds 255 UTF-8 bytes")
    return path


def validate_layout(layout: Any) -> dict[str, Any]:
    if not isinstance(layout, dict) or set(layout) != {"profile", "interpreter", "scheme"}:
        _fail("layout requires exactly profile, interpreter, and scheme")
    if layout["profile"] != PROFILE:
        _fail(f"unsupported layout profile; expected {PROFILE}")
    scheme = layout["scheme"]
    if not isinstance(scheme, dict) or set(scheme) != SCHEMES:
        _fail("layout scheme requires purelib, platlib, scripts, headers, and data")
    for path in scheme.values():
        _safe_path(path, absolute=True)
    _safe_path(layout["interpreter"], absolute=True)
    if layout["interpreter"] == "/":
        _fail("interpreter must name a file")
    return {"profile": PROFILE, "interpreter": layout["interpreter"], "scheme": dict(sorted(scheme.items()))}


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _snapshot(path: Path, limit: int) -> bytes:
    # O_NONBLOCK prevents a FIFO masquerading as a wheel from hanging at open().
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            _fail("input must be a regular local file")
        if info.st_size > limit:
            _fail(f"input exceeds {limit} bytes")
        data = stream.read(limit + 1)
        if len(data) > limit:
            _fail(f"input exceeds {limit} bytes")
        return data


def load_layout(path: str | Path) -> dict[str, Any]:
    data = _snapshot(Path(path), LIMITS["layout_bytes"])
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=lambda _: _fail("non-finite JSON value"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise InvalidInput("layout must be strict UTF-8 JSON") from exc
    return validate_layout(value)


def _check_extra(extra: bytes) -> None:
    position = 0
    while position < len(extra):
        if position + 4 > len(extra):
            _fail("malformed ZIP extra field")
        kind, length = struct.unpack_from("<HH", extra, position)
        position += 4
        if kind == 1:
            _fail("ZIP64 member extra field is unsupported")
        if position + length > len(extra):
            _fail("malformed ZIP extra field length")
        position += length


def _check_directory_budget(data: bytes) -> None:
    """Bound central-directory object creation before zipfile parses it.

    Support ordinary single-disk ZIP only; ZIP64 and prepended/trailing data are
    deliberately outside this small-artifact profile. Never trust count alone.
    """
    end = data.rfind(b"PK\x05\x06", max(0, len(data) - 65557))
    if end < 0 or end + 22 > len(data):
        _fail("missing ordinary ZIP end record")
    _, disk, start_disk, disk_count, count, size, offset, comment = struct.unpack_from("<4s4H2IH", data, end)
    if disk or start_disk or disk_count != count:
        _fail("multi-disk ZIP is unsupported")
    if count == 65535 or size == 0xFFFFFFFF or offset == 0xFFFFFFFF:
        _fail("ZIP64 is unsupported")
    if end + 22 + comment != len(data) or offset + size != end:
        _fail("ZIP64, prepended data, or inconsistent ZIP directory is unsupported")
    if count > LIMITS["wheel_entries"]:
        _fail("wheel entry limit exceeded")
    position = offset
    actual = 0
    while position < end:
        if position + 46 > end or data[position:position + 4] != b"PK\x01\x02":
            _fail("malformed ZIP central directory")
        name_size, extra_size, comment_size = struct.unpack_from("<3H", data, position + 28)
        needed = struct.unpack_from("<H", data, position + 6)[0]
        compressed, expanded = struct.unpack_from("<II", data, position + 20)
        member_disk = struct.unpack_from("<H", data, position + 34)[0]
        local_offset = struct.unpack_from("<I", data, position + 42)[0]
        if needed >= 45 or compressed == 0xFFFFFFFF or expanded == 0xFFFFFFFF or local_offset == 0xFFFFFFFF:
            _fail("ZIP64 or unsupported extraction version")
        if member_disk:
            _fail("multi-disk ZIP member is unsupported")
        central_extra = position + 46 + name_size
        if central_extra + extra_size > end:
            _fail("ZIP central extra field exceeds bounds")
        _check_extra(data[central_extra:central_extra + extra_size])
        if local_offset + 30 > offset or data[local_offset:local_offset + 4] != b"PK\x03\x04":
            _fail("malformed ZIP local header")
        local_needed = struct.unpack_from("<H", data, local_offset + 4)[0]
        local_compressed, local_expanded = struct.unpack_from("<II", data, local_offset + 18)
        if local_needed >= 45 or local_compressed == 0xFFFFFFFF or local_expanded == 0xFFFFFFFF:
            _fail("ZIP64 or unsupported local extraction version")
        local_name, local_extra_size = struct.unpack_from("<HH", data, local_offset + 26)
        local_extra = local_offset + 30 + local_name
        if local_extra + local_extra_size > offset:
            _fail("ZIP local extra field exceeds bounds")
        _check_extra(data[local_extra:local_extra + local_extra_size])
        position += 46 + name_size + extra_size + comment_size
        actual += 1
        if position > end or actual > LIMITS["wheel_entries"]:
            _fail("ZIP directory entry or count exceeds bounds")
    if actual != count:
        _fail("ZIP directory count mismatch")
    if count and not data.startswith(b"PK\x03\x04"):
        _fail("prepended ZIP data is unsupported")


def _metadata(data: bytes, label: str):
    try:
        data.decode("utf-8")
    except UnicodeError as exc:
        raise InvalidInput(f"{label} must be UTF-8") from exc
    # Match installer.utils.parse_metadata_file: raw compat32 scalar values.
    # RFC 2047 decoding/unfolding could accept a different Root-Is-Purelib.
    message = Parser(policy=policy.compat32).parsestr(data.decode("utf-8"))
    if message.defects:
        _fail(f"malformed {label} headers")
    return message


def _one(message, key: str) -> str:
    values = message.get_all(key, [])
    if len(values) != 1:
        _fail(f"metadata requires exactly one {key}")
    return str(values[0])


class TrackingWheel(WheelFile):
    """WheelFile source with provenance for the currently streamed member."""
    current_member = ""

    def get_contents(self):
        for record, stream, executable in super().get_contents():
            self.current_member = record[0]
            yield record, stream, executable


def _validate_wheel(source: TrackingWheel, archive: zipfile.ZipFile, name: str) -> tuple[str, str, int, int]:
    distribution, version, _, filename_tags = parse_wheel_filename(name)
    entries = archive.infolist()
    if len(entries) > LIMITS["wheel_entries"]:
        _fail("wheel entry limit exceeded")
    total = sum(info.file_size for info in entries)
    if total > LIMITS["wheel_uncompressed_bytes"]:
        _fail("wheel uncompressed byte limit exceeded")
    seen = set()
    files = {}
    for info in entries:
        member = info.filename
        if info.orig_filename != member:
            _fail("truncated ZIP member name")
        _safe_path(member, directory=info.is_dir())
        if member in seen:
            _fail(f"duplicate ZIP member: {member}")
        seen.add(member)
        if info.file_size > LIMITS["member_bytes"]:
            _fail(f"member byte limit exceeded: {member}")
        if info.flag_bits & 1 or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            _fail("encrypted or unsupported ZIP compression")
        mode_type = stat.S_IFMT(info.external_attr >> 16)
        allowed = (0, stat.S_IFDIR) if info.is_dir() else (0, stat.S_IFREG)
        if mode_type not in allowed:
            _fail(f"symlink, special, or inconsistent ZIP member type: {member}")
        if info.is_dir():
            if info.file_size:
                _fail("directory entry contains data")
            with archive.open(info) as stream:
                if stream.read(1):
                    _fail("directory entry contains data")
        else:
            files[member] = info
    dist_info = source.dist_info_dir
    di_name, sep, di_version = dist_info[:-10].rpartition("-")
    if not sep or canonicalize_name(di_name) != distribution or Version(di_version) != version:
        _fail("dist-info identity differs from wheel filename")
    for info in entries:
        top = info.filename.split("/", 1)[0]
        if top.startswith(source.data_dir) and top != source.data_dir:
            _fail("ambiguous .data prefix unsupported by pinned installer")
        if top.startswith(dist_info) and top != dist_info:
            _fail("ambiguous dist-info prefix unsupported by pinned installer")
        if top.endswith(".data"):
            if top != source.data_dir:
                _fail(".data directory identity differs from wheel filename")
            parts = info.filename.rstrip("/").split("/")
            if len(parts) == 1 and info.is_dir():
                continue
            if len(parts) < 2 or parts[1] not in SCHEMES:
                _fail("unknown .data destination scheme")
            if len(parts) < 3 and not info.is_dir():
                _fail(".data destination must contain a relative file path")
        if info.filename.startswith(dist_info + "/") and info.file_size > LIMITS["metadata_bytes"]:
            _fail("dist-info metadata byte limit exceeded")
    required = [f"{dist_info}/{key}" for key in ("METADATA", "WHEEL", "RECORD")]
    if any(f"{dist_info}/{signature}" in files for signature in ("RECORD.jws", "RECORD.p7s")):
        _fail("wheel signature sidecars are unsupported")
    if any(member not in files for member in required):
        _fail("wheel requires METADATA, WHEEL, and RECORD")
    wheel = _metadata(archive.read(required[1]), "WHEEL")
    if _one(wheel, "Wheel-Version") != "1.0":
        _fail("only Wheel-Version 1.0 is supported")
    if _one(wheel, "Root-Is-Purelib") not in ("true", "false"):
        _fail("Root-Is-Purelib must be true or false")
    tags = set()
    for tag in wheel.get_all("Tag", []):
        tags.update(parse_tag(str(tag)))
    if tags != filename_tags:
        _fail("WHEEL Tag values must match the filename tags")
    metadata = _metadata(archive.read(required[0]), "METADATA")
    metadata_version = _one(metadata, "Metadata-Version")
    if metadata_version not in {"1.0", "1.1", "1.2", "2.0", "2.1", "2.2", "2.3", "2.4"}:
        _fail("unsupported Metadata-Version (supported through 2.4)")
    metadata_name = _one(metadata, "Name")
    if not _NAME.fullmatch(metadata_name) or canonicalize_name(metadata_name) != distribution:
        _fail("METADATA Name differs from wheel filename")
    if Version(_one(metadata, "Version")) != version:
        _fail("METADATA Version differs from wheel filename")
    generated = 0
    entrypoints = f"{dist_info}/entry_points.txt"
    if entrypoints in files:
        text = archive.read(entrypoints).decode("utf-8")
        config = configparser.ConfigParser(interpolation=None, delimiters="=")
        config.optionxform = str
        config.read_string(text)
        if config.defaults():
            _fail("entry point DEFAULT inheritance is unsupported")
        for section in ("console_scripts", "gui_scripts"):
            if not config.has_section(section):
                continue
            for command, value in config.items(section):
                _safe_path(command)
                if "/" in command or command != command.strip():
                    _fail("generated command must be a single filename")
                if not _OBJECT.fullmatch(value):
                    _fail("unsupported or malformed command object reference")
        # Verify pinned installer's parser accepts the same commands before projection.
        for _ in parse_entrypoints(text):
            generated += 1
            if generated + len(entries) > LIMITS["wheel_entries"]:
                _fail("wheel entry limit exceeded including generated commands")
    record_name = required[2]
    rows = {}
    for row in csv.reader(io.StringIO(archive.read(record_name).decode("utf-8")), strict=True):
        if len(row) != 3:
            _fail("RECORD must have exactly three CSV columns")
        member, digest, size = row
        _safe_path(member)
        if member in rows:
            _fail(f"duplicate RECORD path: {member}")
        rows[member] = (digest, size)
    if set(rows) != set(files):
        _fail("RECORD paths must exactly match archive files; signature sidecars unsupported")
    for member, info in files.items():
        digest, size = rows[member]
        if member == record_name:
            if digest or size:
                _fail("RECORD self-entry must have empty hash and size")
            continue
        if len(size) > 20 or not size.isascii() or not size.isdigit() or int(size) != info.file_size:
            _fail(f"RECORD size mismatch: {member}")
        algorithm, sep, expected = digest.partition("=")
        if not sep or algorithm not in {"sha256", "sha384", "sha512"}:
            _fail("only sha256/sha384/sha512 RECORD hashes are supported")
        hasher = hashlib.new(algorithm)
        count = 0
        with archive.open(info) as stream:
            while block := stream.read(64 * 1024):
                count += len(block)
                if count > info.file_size or count > LIMITS["member_bytes"]:
                    _fail("decompressed member exceeds declared size or limit")
                hasher.update(block)
        actual = base64.urlsafe_b64encode(hasher.digest()).decode("ascii").rstrip("=")
        if count != info.file_size or actual != expected:
            _fail(f"RECORD hash mismatch: {member}")
    return str(distribution), str(version), total, len(entries) + generated


class RecordingDestination(SchemeDictionaryDestination):
    """No filesystem writes: use PyPA transforms and record intended writes."""
    def __init__(self, layout: dict[str, Any], source: TrackingWheel, owner: dict[str, str]):
        super().__init__(layout["scheme"], layout["interpreter"], "posix", bytecode_optimization_levels=())
        self.source = source
        self.owner = owner
        self.claims: list[dict[str, Any]] = []
        self.context: tuple[str, str] | None = None

    def write_to_fs(self, scheme, path, stream, is_executable):
        _safe_path(path)
        target = posixpath.join(self.scheme_dict[scheme], path)
        _safe_path(target, absolute=True)
        sha = hashlib.sha256()
        count = 0
        while block := stream.read(64 * 1024):
            count += len(block)
            # Rewritten shebangs and generated RECORD may be larger than an input member.
            if count > LIMITS["member_bytes"] + LIMITS["metadata_bytes"]:
                _fail("projected file byte limit exceeded")
            sha.update(block)
        kind, origin = self.context or ("raw-script" if scheme == "scripts" else "file", self.source.current_member)
        self.claims.append({"path": target, "scheme": scheme, "relative_path": path,
                            "kind": kind, "source": origin, "sha256": sha.hexdigest(),
                            "size": count, "executable": bool(is_executable), **self.owner})
        encoded = base64.urlsafe_b64encode(sha.digest()).decode("ascii").rstrip("=")
        return RecordEntry(path, Hash("sha256", encoded), count)

    def write_script(self, name, module, attr, section):
        # Parent write_script calls stat/chmod after write_to_fs. Generate with the
        # same public Script API, omitting those filesystem-only operations.
        script_name, data = Script(name, module, attr, section).generate(self.interpreter, "posix")
        self.context = (f"generated-{section}", f"{name} = {module}:{attr}")
        try:
            return self.write_to_fs("scripts", script_name, io.BytesIO(data), True)
        finally:
            self.context = None

    def finalize_installation(self, scheme, record_file_path, records):
        self.context = ("generated-record", record_file_path)
        try:
            return super().finalize_installation(scheme, record_file_path, records)
        finally:
            self.context = None

    def _compile_bytecode(self, scheme, record):
        # Deliberate invariant even if upstream changes empty-level behavior.
        return None


def _claim_key(claim: dict[str, Any]):
    return (claim["path"], claim["distribution"], claim["wheel"], claim["kind"], claim["source"], claim["scheme"])


def _conflicts(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_path = defaultdict(list)
    for claim in claims:
        by_path[claim["path"]].append(claim)
    conflicts = []
    references = len(claims)

    def charge(count):
        nonlocal references
        references += count
        if references > LIMITS["report_claim_references"]:
            _fail("report claim-reference limit exceeded")

    for path in sorted(by_path):
        owners = by_path[path]
        if len(owners) > 1:
            charge(len(owners))
            same = len({(c["sha256"], c["size"]) for c in owners}) == 1
            commands = any(c["kind"].startswith("generated-") and c["kind"] != "generated-record" for c in owners)
            conflicts.append({"type": "shared-file", "path": path,
                              "content": "identical" if same else "different",
                              "command_overlap": commands, "claims": owners})
    # A shared namespace directory is harmless. A file at any ancestor is not.
    children = defaultdict(list)
    for path, owners in by_path.items():
        parent = posixpath.dirname(path)
        while parent != "/":
            if parent in by_path:
                charge(len(owners))
                children[parent].extend(owners)
            parent = posixpath.dirname(parent)
    for path in sorted(children):
        charge(len(by_path[path]))
        conflicts.append({"type": "file-directory", "path": path,
                          "file_claims": by_path[path], "descendant_claims": sorted(children[path], key=_claim_key)})
    return sorted(conflicts, key=lambda item: (item["path"], item["type"]))


def invalid_report(message: str) -> dict[str, Any]:
    return {"schema_version": 1, "status": "invalid", "profile": PROFILE,
            "layout": None, "wheels": [], "claims": [], "conflicts": [],
            "errors": [{"wheel": None, "message": message}], "limits": LIMITS.copy()}


def audit(wheels: list[str | Path], layout: dict[str, Any]) -> dict[str, Any]:
    """Return schema v1 report. Invalid sets never expose partial clean claims.

    The caller supplies an already-resolved, explicit set of local wheel files.
    A clean report is limited to this POSIX projection and this complete set.
    """
    try:
        layout = validate_layout(layout)
        if os.name != "posix":
            _fail("projection must run on a POSIX host")
        if importlib.metadata.version("installer") != "0.7.0":
            _fail("installer 0.7.0 is required; API compatibility is pinned")
        if not wheels or len(wheels) > LIMITS["wheels"]:
            _fail(f"provide between 1 and {LIMITS['wheels']} explicit wheel paths")
    except (ValueError, importlib.metadata.PackageNotFoundError) as exc:
        return invalid_report(str(exc))
    reports = []
    claims = []
    errors = []
    distributions = set()
    total = entries = archive_total = 0
    for path in sorted((Path(p) for p in wheels), key=lambda p: (p.name, str(p))):
        try:
            data = _snapshot(path, min(LIMITS["archive_bytes"], LIMITS["set_archive_bytes"] - archive_total))
            archive_total += len(data)
            if archive_total > LIMITS["set_archive_bytes"]:
                _fail("whole-set archive byte limit exceeded")
            _check_directory_budget(data)
            digest = hashlib.sha256(data).hexdigest()
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                archive.filename = path.name
                # Charge declared resources before decompression, even for invalid wheels.
                total += sum(info.file_size for info in archive.infolist())
                entries += len(archive.infolist())
                if total > LIMITS["set_uncompressed_bytes"] or entries > LIMITS["set_entries"]:
                    _fail("whole-set resource limit exceeded")
                source = TrackingWheel(archive)
                distribution, version, _, projected_count = _validate_wheel(source, archive, path.name)
                entries += projected_count - len(archive.infolist())
                if entries > LIMITS["set_entries"]:
                    _fail("whole-set entry limit exceeded including generated commands")
                if distribution in distributions:
                    _fail(f"multiple artifacts for normalized distribution: {distribution}")
                distributions.add(distribution)
                owner = {"distribution": distribution, "version": version, "wheel": path.name}
                destination = RecordingDestination(layout, source, owner)
                install(source, destination, additional_metadata={})
                claims.extend(destination.claims)
                reports.append({**owner, "archive_sha256": digest})
        except Exception as exc:
            # Input parsers expose several exception types (including assertions).
            # Treat every per-artifact projection failure as invalid, never clean.
            errors.append({"wheel": path.name, "message": f"{type(exc).__name__}: {exc}"})
            if total > LIMITS["set_uncompressed_bytes"] or entries > LIMITS["set_entries"]:
                break
    claims.sort(key=_claim_key)
    try:
        conflicts = _conflicts(claims) if not errors else []
    except InvalidInput as exc:
        errors.append({"wheel": None, "message": str(exc)})
        conflicts = []
    report = {"schema_version": 1, "status": "invalid" if errors else "conflict" if conflicts else "clean",
            "profile": PROFILE, "layout": layout,
            "wheels": sorted(reports, key=lambda w: (w["distribution"], w["wheel"])),
            "claims": claims if not errors else [], "conflicts": conflicts,
            "errors": errors, "limits": LIMITS.copy()}
    # Measure a streaming encoding before returning the report. This avoids
    # materializing oversized JSON when many ancestor conflicts repeat claims.
    encoded_size = 1  # CLI final newline
    for chunk in json.JSONEncoder(ensure_ascii=True, indent=2, sort_keys=True).iterencode(report):
        encoded_size += len(chunk)  # ensure_ascii makes character count byte count
        if encoded_size > LIMITS["report_bytes"]:
            return invalid_report("report byte limit exceeded")
    return report
