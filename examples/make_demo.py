"""Create four tiny inert wheels for the README examples. No third-party inputs."""
from __future__ import annotations

import base64
import csv
import hashlib
import io
from pathlib import Path
import zipfile


def wheel(root: Path, name: str, files: dict[str, bytes], command: str | None = None) -> None:
    dist = f"{name}-1.0.dist-info"
    contents = dict(files)
    contents[f"{dist}/METADATA"] = f"Metadata-Version: 2.4\nName: {name}\nVersion: 1.0\n".encode()
    contents[f"{dist}/WHEEL"] = b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    if command:
        contents[f"{dist}/entry_points.txt"] = f"[console_scripts]\nacme = {command}:main\n".encode()
    record = io.StringIO(newline="")
    writer = csv.writer(record, lineterminator="\n")
    for path, data in contents.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")
        writer.writerow((path, f"sha256={digest}", len(data)))
    writer.writerow((f"{dist}/RECORD", "", ""))
    contents[f"{dist}/RECORD"] = record.getvalue().encode()
    with zipfile.ZipFile(root / f"{name}-1.0-py3-none-any.whl", "w") as archive:
        for path, data in contents.items():
            info = zipfile.ZipInfo(path, (2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)


if __name__ == "__main__":
    root = Path(__file__).parent / "generated"
    root.mkdir(exist_ok=True)
    wheel(root, "alpha", {"acme/common.py": b"VALUE = 'alpha'\n"}, "acme.common")
    wheel(root, "beta", {"beta-1.0.data/purelib/acme/common.py": b"VALUE = 'beta'\n"}, "beta.cli")
    wheel(root, "namespace_a", {"acme/a.py": b"VALUE = 'a'\n"})
    wheel(root, "namespace_b", {"acme/b.py": b"VALUE = 'b'\n"})
    print(f"Wrote four inert demonstration wheels to {root}")
