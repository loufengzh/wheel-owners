import copy
import hashlib
import json
import os
import stat
import subprocess
import sys
import zipfile

import pytest

from wheel_owners.audit import LIMITS, audit, load_layout
from helpers import make_wheel


def shared(report, suffix):
    return next(c for c in report["conflicts"] if c["path"].endswith(suffix))


def test_required_composition_case(tmp_path, layout):
    alpha = make_wheel(tmp_path, "alpha", files={"acme/common.py": b"VALUE = 1\n"},
                       entrypoints="[console_scripts]\nacme = acme.common:main\n")
    beta = make_wheel(tmp_path, "beta", files={"beta-1.0.data/purelib/acme/common.py": b"VALUE = 2\n"},
                      entrypoints="[console_scripts]\nacme = beta.cli:main\n")
    report = audit([alpha, beta], layout)
    assert report["status"] == "conflict", report["errors"]
    assert shared(report, "/acme/common.py")["content"] == "different"
    assert shared(report, "/bin/acme")["command_overlap"]
    assert len(report["conflicts"]) == 2
    assert report == audit([beta, alpha], layout)


def test_namespace_sharing_passes(tmp_path, layout):
    alpha = make_wheel(tmp_path, "alpha", files={"acme/a.py": b"raise RuntimeError('never execute')\n"}, directories=["acme/"])
    beta = make_wheel(tmp_path, "beta", files={"acme/b.py": b"raise RuntimeError('never execute')\n"}, directories=["acme/"])
    report = audit([alpha, beta], layout)
    assert report["status"] == "clean", report["errors"]
    assert not report["conflicts"]


def test_identical_content_still_conflicts(tmp_path, layout):
    a = make_wheel(tmp_path, files={"acme/common.py": b"same"})
    b = make_wheel(tmp_path, "beta", files={"acme/common.py": b"same"})
    conflict = shared(audit([a, b], layout), "/acme/common.py")
    assert conflict["content"] == "identical"
    assert not conflict["command_overlap"]


@pytest.mark.parametrize("scheme", ["purelib", "platlib", "scripts", "headers", "data"])
def test_all_data_schemes_and_aliases(tmp_path, layout, scheme):
    layout["scheme"] = dict.fromkeys(layout["scheme"], "/target")
    a = make_wheel(tmp_path, files={"same": b"root"})
    b = make_wheel(tmp_path, "beta", files={f"beta-1.0.data/{scheme}/same": b"data"})
    assert shared(audit([a, b], layout), "/same")["type"] == "shared-file"


def test_platlib_root_is_not_purelib(tmp_path, layout):
    layout["scheme"]["platlib"] = "/native"
    a = make_wheel(tmp_path, files={"same": b"root"})
    b = make_wheel(tmp_path, "beta", files={"same": b"root"}, pure=False)
    report = audit([a, b], layout)
    assert report["status"] == "clean"
    assert any(c["path"] == "/native/same" for c in report["claims"])


def test_console_gui_raw_script_overlap(tmp_path, layout):
    a = make_wheel(tmp_path, entrypoints="[console_scripts]\nrun = alpha:main\n")
    b = make_wheel(tmp_path, "beta", entrypoints="[gui_scripts]\nrun = beta:main\n")
    c = make_wheel(tmp_path, "gamma", files={"gamma-1.0.data/scripts/run": b"#!python\npass\n"})
    conflict = shared(audit([a, b, c], layout), "/bin/run")
    assert conflict["command_overlap"]
    assert {c["kind"] for c in conflict["claims"]} == {"generated-console", "generated-gui", "raw-script"}


def test_file_directory_conflict(tmp_path, layout):
    a = make_wheel(tmp_path, files={"acme": b"file"})
    b = make_wheel(tmp_path, "beta", files={"acme/nested/code.py": b"pass"})
    conflict = shared(audit([a, b], layout), "/acme")
    assert conflict["type"] == "file-directory"
    assert conflict["descendant_claims"][0]["source"] == "acme/nested/code.py"


def test_scheme_parent_collision(tmp_path, layout):
    a = make_wheel(tmp_path, files={"alpha-1.0.data/data/bin": b"file"})
    b = make_wheel(tmp_path, "beta", entrypoints="[console_scripts]\nrun = beta:main\n")
    assert shared(audit([a, b], layout), "/bin")["type"] == "file-directory"


def test_intra_wheel_alias_is_conflict(tmp_path, layout):
    a = make_wheel(tmp_path, files={"x": b"1", "alpha-1.0.data/purelib/x": b"2"})
    assert audit([a], layout)["status"] == "conflict"


@pytest.mark.parametrize("other", ["alpha", "Alpha", "alpha" + "_" + "pkg"])
def test_normalized_distribution_duplicates(tmp_path, layout, other):
    name = "alpha_pkg" if other == "alpha_pkg" else "alpha"
    a = make_wheel(tmp_path / "first", name=name)
    b = make_wheel(tmp_path / "second", name=other, version="2.0")
    report = audit([a, b], layout)
    assert report["status"] == "invalid"
    assert "multiple artifacts" in str(report["errors"])
    assert report["claims"] == []


@pytest.mark.parametrize("path", ["../escape", "/absolute", "a/../b", "a/./b", "a//b", "a\\b", "a\x00tail", "a\nb", "a/" * 65 + "b"])
def test_reject_bad_member_paths(tmp_path, layout, path):
    a = make_wheel(tmp_path, files={path: b"x"})
    assert audit([a], layout)["status"] == "invalid"


@pytest.mark.parametrize("path", ["alpha-1.0.datax/x", "alpha-1.0.data/x/x", "alpha-1.0.data/scripts", "other-1.0.data/data/x", "alpha-1.0.dist-info.extra/x"])
def test_reject_ambiguous_data_and_metadata_paths(tmp_path, layout, path):
    a = make_wheel(tmp_path, files={path: b"x"})
    assert audit([a], layout)["status"] == "invalid"


@pytest.mark.parametrize("wheel_text", [
    "Wheel-Version: 2.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    "Wheel-Version: 1.1\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    "Wheel-Version: 1.0\nRoot-Is-Purelib: maybe\nTag: py3-none-any\n",
    "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nRoot-Is-Purelib: false\nTag: py3-none-any\n",
    "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py2-none-any\n",
])
def test_reject_unsupported_wheel_metadata(tmp_path, layout, wheel_text):
    assert audit([make_wheel(tmp_path, wheel_text=wheel_text)], layout)["status"] == "invalid"


@pytest.mark.parametrize("ep", [
    "[console_scripts]\n../run = alpha:main\n", "[console_scripts]\n/run = alpha:main\n",
    "[console_scripts]\nrun = alpha\n", "[console_scripts]\nrun = alpha:main;malicious\n",
    "[console_scripts]\nrun = alpha:main\nrun = alpha:other\n",
    "[DEFAULT]\nrun = alpha:main\n[console_scripts]\n",
])
def test_reject_malformed_entrypoints(tmp_path, layout, ep):
    assert audit([make_wheel(tmp_path, entrypoints=ep)], layout)["status"] == "invalid"


def test_entrypoint_extras_and_custom_groups(tmp_path, layout):
    a = make_wheel(tmp_path, entrypoints="[console_scripts]\nrun = alpha:main [cli]\n[plugins]\nanything = a.b\n")
    assert audit([a], layout)["status"] == "clean"


def test_symlink_rejected(tmp_path, layout):
    a = make_wheel(tmp_path, files={"link": b"target"}, modes={"link": stat.S_IFLNK | 0o777})
    assert audit([a], layout)["status"] == "invalid"


def test_duplicate_zip_member_rejected(tmp_path, layout):
    a = make_wheel(tmp_path, files={"a": b"original"})
    with pytest.warns(UserWarning), zipfile.ZipFile(a, "a") as archive:
        archive.writestr("a", b"duplicate")
    assert audit([a], layout)["status"] == "invalid"


@pytest.mark.parametrize("record", ["alpha-1.0.dist-info/RECORD,,\n", "a,sha256=wrong,1\nalpha-1.0.dist-info/RECORD,,\n", "one,two\n"])
def test_bad_record_is_invalid(tmp_path, layout, record):
    assert audit([make_wheel(tmp_path, record_text=record)], layout)["status"] == "invalid"


def test_tampered_record_hash(tmp_path, layout):
    a = make_wheel(tmp_path, files={"x": b"yes"})
    with zipfile.ZipFile(a) as z:
        contents = {n: z.read(n) for n in z.namelist()}
    contents["x"] = b"bad"
    with zipfile.ZipFile(a, "w") as z:
        for n, b in contents.items():
            z.writestr(n, b)
    assert "hash mismatch" in str(audit([a], layout)["errors"])


@pytest.mark.parametrize("key", ["archive_bytes", "member_bytes", "metadata_bytes", "wheel_uncompressed_bytes", "set_uncompressed_bytes", "wheel_entries", "set_entries"])
def test_limits_fail_closed(tmp_path, layout, monkeypatch, key):
    a = make_wheel(tmp_path, files={"x": b"hello"})
    monkeypatch.setitem(LIMITS, key, 1)
    assert audit([a], layout)["status"] == "invalid"


@pytest.mark.parametrize("path", ["relative", "/v/../x", "/v//x", "/v/", "//v", "/v\\x"])
def test_layout_paths_are_explicit_and_normalized(layout, path):
    layout["scheme"]["purelib"] = path
    assert audit(["unused.whl"], layout)["status"] == "invalid"


def test_duplicate_json_keys(tmp_path):
    path = tmp_path / "layout.json"
    path.write_text('{"profile":"one","profile":"two"}')
    with pytest.raises(ValueError, match="duplicate JSON"):
        load_layout(path)


def test_non_regular_input_fails_without_hang(tmp_path, layout):
    a = tmp_path / "alpha-1.0-py3-none-any.whl"
    os.mkfifo(a)
    assert audit([a], layout)["status"] == "invalid"


def test_does_not_write_or_execute(tmp_path, layout, monkeypatch):
    import compileall
    a = make_wheel(tmp_path, files={"payload.py": b"raise RuntimeError('MUST NOT RUN')"},
                   entrypoints="[console_scripts]\nrun = payload:main\n")
    def forbidden(*args, **kwargs):
        raise AssertionError("filesystem write or execution attempted")
    monkeypatch.setattr(os, "mkdir", forbidden)
    monkeypatch.setattr(os, "chmod", forbidden)
    monkeypatch.setattr(compileall, "compile_file", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    assert audit([a], layout)["status"] == "clean"


def test_unicode_is_codepoint_exact_and_case_sensitive(tmp_path, layout):
    a = make_wheel(tmp_path, files={"café/a": b"1", "Case": b"1"})
    b = make_wheel(tmp_path, "beta", files={"cafe\u0301/a": b"2", "case": b"2"})
    assert audit([a, b], layout)["status"] == "clean"


def test_cli_exit_codes_json(tmp_path, layout):
    layout_path = tmp_path / "layout.json"
    layout_path.write_text(json.dumps(layout))
    a = make_wheel(tmp_path, files={"x": b"1"})
    b = make_wheel(tmp_path, "beta", files={"x": b"2"})
    for args, code, status in [([str(a)], 0, "clean"), ([str(a), str(b)], 1, "conflict"), (["missing.whl"], 2, "invalid")]:
        process = subprocess.run([sys.executable, "-m", "wheel_owners", "--layout", str(layout_path), *args], text=True, capture_output=True)
        assert process.returncode == code, process.stderr
        assert json.loads(process.stdout)["status"] == status
        assert not process.stderr


def test_cli_argument_error_is_json():
    process = subprocess.run([sys.executable, "-m", "wheel_owners"], text=True, capture_output=True)
    assert process.returncode == 2
    assert json.loads(process.stdout)["status"] == "invalid"


def test_normalized_underscore_dot_duplicate(tmp_path, layout):
    a = make_wheel(tmp_path, name="alpha_pkg")
    b = make_wheel(tmp_path, name="Alpha.Pkg", version="2.0")
    report = audit([a, b], layout)
    assert report["status"] == "invalid"
    assert "multiple artifacts" in str(report["errors"])


def test_record_signature_is_explicitly_unsupported(tmp_path, layout):
    a = make_wheel(tmp_path, files={"alpha-1.0.dist-info/RECORD.jws": b"opaque"})
    assert "signature" in str(audit([a], layout)["errors"])


def test_generated_record_claim_cannot_be_overwritten(tmp_path, layout):
    a = make_wheel(tmp_path)
    b = make_wheel(tmp_path, "beta", files={"beta-1.0.data/purelib/alpha-1.0.dist-info/RECORD": b"fake"})
    report = audit([a, b], layout)
    assert shared(report, "/alpha-1.0.dist-info/RECORD")["content"] == "different"


def test_set_budget_precedes_decompression(tmp_path, layout, monkeypatch):
    a = make_wheel(tmp_path)
    monkeypatch.setitem(LIMITS, "set_uncompressed_bytes", 1)
    def forbidden(*a, **k):
        raise AssertionError("read before resource check")
    monkeypatch.setattr(zipfile.ZipFile, "read", forbidden)
    report = audit([a], layout)
    assert "whole-set resource limit" in str(report["errors"])


def test_deep_layout_json_returns_invalid(tmp_path):
    path = tmp_path / "layout.json"
    path.write_text("[" * 3000 + "]" * 3000)
    process = subprocess.run([sys.executable, "-m", "wheel_owners", "--layout", str(path), "x.whl"], text=True, capture_output=True)
    assert process.returncode == 2
    assert json.loads(process.stdout)["status"] == "invalid"


def test_all_identical_generated_commands_still_conflict(tmp_path, layout):
    ep = "[console_scripts]\nrun = common:main\n"
    a = make_wheel(tmp_path, entrypoints=ep)
    b = make_wheel(tmp_path, "beta", entrypoints=ep)
    conflict = shared(audit([a, b], layout), "/bin/run")
    assert conflict["command_overlap"] and conflict["content"] == "identical"


def test_fake_central_count_is_rejected_before_zipfile(tmp_path, layout, monkeypatch):
    import struct
    a = make_wheel(tmp_path)
    data = bytearray(a.read_bytes())
    end = data.rfind(b"PK\x05\x06")
    struct.pack_into("<HH", data, end + 8, 1, 1)
    a.write_bytes(data)
    class ForbiddenZip:
        def __init__(self, *args, **kwargs):
            raise AssertionError("directory budget was bypassed")
    monkeypatch.setattr(zipfile, "ZipFile", ForbiddenZip)
    assert "directory count mismatch" in str(audit([a], layout)["errors"])


def test_zip_trailing_data_fails_closed(tmp_path, layout):
    a = make_wheel(tmp_path)
    a.write_bytes(a.read_bytes() + b"trailing")
    assert audit([a], layout)["status"] == "invalid"


def test_wheel_with_zip_comment_passes(tmp_path, layout):
    a = make_wheel(tmp_path)
    with zipfile.ZipFile(a, "a") as archive:
        archive.comment = b"ordinary archive comment"
    assert audit([a], layout)["status"] == "clean"


def test_generated_commands_count_toward_entry_budget(tmp_path, layout, monkeypatch):
    a = make_wheel(tmp_path, entrypoints="[console_scripts]\na = alpha:main\nb = alpha:main\n")
    monkeypatch.setitem(LIMITS, "wheel_entries", 5)
    assert "including generated commands" in str(audit([a], layout)["errors"])


def test_generated_commands_count_toward_set_budget(tmp_path, layout, monkeypatch):
    a = make_wheel(tmp_path, entrypoints="[console_scripts]\na = alpha:main\nb = alpha:main\n")
    monkeypatch.setitem(LIMITS, "set_entries", 5)
    assert "including generated commands" in str(audit([a], layout)["errors"])


@pytest.mark.parametrize("scalar", ["=?utf-8?q?true?=", "true\n ", "true\t", "true\n\t"])
def test_root_scalar_uses_installer_raw_header_semantics(tmp_path, layout, scalar):
    layout["scheme"]["platlib"] = "/separate-platlib"
    wheel_text = f"Wheel-Version: 1.0\nRoot-Is-Purelib: {scalar}\nTag: py3-none-any\n"
    a = make_wheel(tmp_path, wheel_text=wheel_text)
    report = audit([a], layout)
    assert report["status"] == "invalid"
    assert "Root-Is-Purelib" in str(report["errors"])


@pytest.mark.parametrize("scalar", ["=?utf-8?q?1.0?=", "1.0\n "])
def test_wheel_version_encoded_or_folded_is_invalid(tmp_path, layout, scalar):
    a = make_wheel(tmp_path, wheel_text=f"Wheel-Version: {scalar}\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
    assert audit([a], layout)["status"] == "invalid"


def test_forced_local_zip64_is_unsupported(tmp_path, layout):
    a = make_wheel(tmp_path)
    with zipfile.ZipFile(a) as archive:
        contents = {n: archive.read(n) for n in archive.namelist()}
    with zipfile.ZipFile(a, "w") as archive:
        for name, content in contents.items():
            with archive.open(name, "w", force_zip64=True) as stream:
                stream.write(content)
    assert "ZIP64" in str(audit([a], layout)["errors"])


def test_central_zip64_extra_is_unsupported(tmp_path, layout):
    import struct
    a = make_wheel(tmp_path)
    with zipfile.ZipFile(a) as archive:
        contents = {n: archive.read(n) for n in archive.namelist()}
    with zipfile.ZipFile(a, "w") as archive:
        for name, content in contents.items():
            info = zipfile.ZipInfo(name)
            info.extra = struct.pack("<HH", 1, 0)
            archive.writestr(info, content)
    assert "ZIP64" in str(audit([a], layout)["errors"])


def test_per_member_multi_disk_rejected(tmp_path, layout):
    import struct
    a = make_wheel(tmp_path)
    data = bytearray(a.read_bytes())
    central = data.index(b"PK\x01\x02")
    struct.pack_into("<H", data, central + 34, 1)
    a.write_bytes(data)
    assert "multi-disk ZIP member" in str(audit([a], layout)["errors"])


@pytest.mark.parametrize("local", [True, False])
def test_zip64_extraction_version_rejected(tmp_path, layout, local):
    import struct
    a = make_wheel(tmp_path)
    data = bytearray(a.read_bytes())
    start = 0 if local else data.index(b"PK\x01\x02")
    struct.pack_into("<H", data, start + (4 if local else 6), 45)
    a.write_bytes(data)
    assert "extraction version" in str(audit([a], layout)["errors"])


def test_report_reference_amplification_is_invalid(tmp_path, layout, monkeypatch):
    a = make_wheel(tmp_path, files={"x": b"1", "x/y": b"2", "x/y/z": b"3"})
    monkeypatch.setitem(LIMITS, "report_claim_references", 8)
    report = audit([a], layout)
    assert report["status"] == "invalid"
    assert not report["claims"] and not report["conflicts"]
    assert "claim-reference limit" in str(report["errors"])


def test_report_size_checked_before_materializing_json(tmp_path, layout, monkeypatch):
    a = make_wheel(tmp_path, files={"x": b"1"})
    monkeypatch.setitem(LIMITS, "report_bytes", 1000)
    report = audit([a], layout)
    assert report["status"] == "invalid"
    assert "report byte limit" in str(report["errors"])
