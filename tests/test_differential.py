"""Compare projection to actual PyPA installer output on inert synthetic wheels.

The actual installer writes only into pytest temp directories, never imports the
fixture packages, and has bytecode compilation disabled. It is not used by CLI.
"""
import hashlib
import stat

import pytest
from installer import install
from installer.destinations import SchemeDictionaryDestination
from installer.sources import WheelFile

from wheel_owners.audit import audit
from helpers import make_wheel


@pytest.mark.parametrize("pure", [True, False])
@pytest.mark.parametrize("aliased", [True, False])
@pytest.mark.parametrize("interpreter", ["/venv/bin/python", "/venv/has space/python"])
def test_exact_destinations_hashes_sizes_modes_and_record(tmp_path, layout, pure, aliased, interpreter):
    layout["interpreter"] = interpreter
    if not aliased:
        layout["scheme"]["platlib"] = "/venv/native"
    files = {
        "acme/module.py": b"raise RuntimeError('MUST NEVER IMPORT')\n",
        "alpha-1.0.data/purelib/acme/pure.py": b"pass\n",
        "alpha-1.0.data/platlib/acme/native.so": b"inert placeholder, not native code",
        "alpha-1.0.data/scripts/raw": b"#!python\nprint('not executed')\n",
        "alpha-1.0.data/scripts/rawgui": b"#!pythonw\npass\n",
        "alpha-1.0.data/scripts/shell": b"#!/bin/sh\nexit 0\n",
        "alpha-1.0.data/data/share/acme/config": b"config",
        "alpha-1.0.data/headers/acme/header.h": b"/* inert */",
    }
    wheel = make_wheel(tmp_path, files=files, pure=pure,
                       modes={"alpha-1.0.data/scripts/raw": stat.S_IFREG | 0o755},
                       entrypoints="[console_scripts]\nacme = acme.module:main\n[gui_scripts]\nacme-gui = acme.module:launch\n")
    report = audit([wheel], layout)
    assert report["status"] == "clean", report["errors"]
    root = tmp_path / "actual"
    with WheelFile.open(wheel) as source:
        destination = SchemeDictionaryDestination(layout["scheme"], interpreter, "posix",
                                                   bytecode_optimization_levels=(), destdir=str(root))
        source.validate_record()
        install(source, destination, additional_metadata={})
    actual = {}
    for path in root.rglob("*"):
        if path.is_file():
            content = path.read_bytes()
            actual["/" + path.relative_to(root).as_posix()] = {
                "sha256": hashlib.sha256(content).hexdigest(),
                "size": len(content), "executable": bool(path.stat().st_mode & 0o111)}
    projected = {c["path"]: {k: c[k] for k in ("sha256", "size", "executable")} for c in report["claims"]}
    assert actual == projected
    assert any(c["kind"] == "generated-record" for c in report["claims"])
    assert not list(root.rglob("*.pyc"))


def test_required_pair_overlap_matches_separate_actual_installs(tmp_path, layout):
    a = make_wheel(tmp_path, files={"acme/common.py": b"first\n"},
                   entrypoints="[console_scripts]\nacme = acme.common:main\n")
    b = make_wheel(tmp_path, "beta", files={"beta-1.0.data/purelib/acme/common.py": b"second\n"},
                   entrypoints="[console_scripts]\nacme = beta:main\n")
    actual_sets = []
    for index, wheel in enumerate([a, b]):
        root = tmp_path / f"actual-{index}"
        with WheelFile.open(wheel) as source:
            install(source, SchemeDictionaryDestination(layout["scheme"], layout["interpreter"], "posix",
                    bytecode_optimization_levels=(), destdir=str(root)), additional_metadata={})
        actual_sets.append({"/" + p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()})
    report = audit([a, b], layout)
    assert {c["path"] for c in report["conflicts"]} == actual_sets[0] & actual_sets[1]
    assert len(report["conflicts"]) == 2


def test_namespace_control_actually_installs_together(tmp_path, layout):
    wheels = [make_wheel(tmp_path, files={"acme/a.py": b"pass\n"}),
              make_wheel(tmp_path, "beta", files={"acme/b.py": b"pass\n"})]
    root = tmp_path / "actual"
    for wheel in wheels:
        with WheelFile.open(wheel) as source:
            install(source, SchemeDictionaryDestination(layout["scheme"], layout["interpreter"], "posix",
                    bytecode_optimization_levels=(), destdir=str(root)), additional_metadata={})
    report = audit(wheels, layout)
    assert report["status"] == "clean"
    assert {c["path"] for c in report["claims"]} == {
        "/" + p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
