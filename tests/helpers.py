"""Tiny, deterministic synthetic wheels. These are test data, never imported."""
import base64
import csv
import hashlib
import io
import stat
import zipfile
from pathlib import Path


def make_wheel(root, name="alpha", version="1.0", files=None, *, pure=True,
               entrypoints=None, wheel_text=None, metadata_text=None, record_text=None,
               modes=None, directories=(), tags="py3-none-any", build=None):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    dist = f"{name}-{version}.dist-info"
    contents = dict(files or {})
    contents[f"{dist}/WHEEL"] = (wheel_text or f"Wheel-Version: 1.0\nGenerator: synthetic-fixture\nRoot-Is-Purelib: {str(pure).lower()}\nTag: {tags}\n").encode()
    contents[f"{dist}/METADATA"] = (metadata_text or f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n").encode()
    if entrypoints is not None:
        contents[f"{dist}/entry_points.txt"] = entrypoints.encode()
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    for path, data in contents.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")
        writer.writerow((path, f"sha256={digest}", len(data)))
    writer.writerow((f"{dist}/RECORD", "", ""))
    contents[f"{dist}/RECORD"] = (record_text if record_text is not None else out.getvalue()).encode()
    build_part = f"-{build}" if build else ""
    path = root / f"{name}-{version}{build_part}-{tags}.whl"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for directory in directories:
            info = zipfile.ZipInfo(directory, (2020, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFDIR | 0o755) << 16
            archive.writestr(info, b"")
        for member, data in contents.items():
            info = zipfile.ZipInfo(member, (2020, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (modes or {}).get(member, stat.S_IFREG | 0o644) << 16
            archive.writestr(info, data)
    return path
