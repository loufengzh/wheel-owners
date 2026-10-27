"""Bound compressed compatibility tags before packaging expands their product."""
import importlib

import pytest

from helpers import make_wheel
from wheel_owners.audit import LIMITS, audit

audit_module = importlib.import_module("wheel_owners.audit")


def wheel_text(*tags):
    return "Wheel-Version: 1.0\nRoot-Is-Purelib: true\n" + "".join(
        f"Tag: {tag}\n" for tag in tags
    )


def forbid(*args, **kwargs):
    pytest.fail("expanding parser must not be reached for oversized tags")


def test_metadata_cartesian_budget_precedes_parse_tag(tmp_path, layout, monkeypatch):
    # Less than 1 KiB of metadata would expand into 512,000 Tag objects.
    tag = "-".join(".".join(f"{prefix}{i}" for i in range(80)) for prefix in "pat")
    wheel = make_wheel(tmp_path, wheel_text=wheel_text("py3-none-any", tag))
    monkeypatch.setattr(audit_module, "parse_tag", forbid)
    report = audit([wheel], layout)
    assert report["status"] == "invalid"
    assert report["errors"][0]["message"] == "InvalidInput: WHEEL tag combination limit exceeded"
    assert report["claims"] == report["conflicts"] == []


@pytest.mark.parametrize("build", [None, "1"])
def test_filename_cartesian_budget_precedes_filename_parser(tmp_path, layout, monkeypatch, build):
    # Repeated subtags consume work even though the resulting set has size one.
    tag = "-".join(".".join([prefix] * 22) for prefix in "pat")
    wheel = make_wheel(tmp_path, tags=tag, build=build)
    monkeypatch.setattr(audit_module, "parse_wheel_filename", forbid)
    report = audit([wheel], layout)
    assert report["status"] == "invalid"
    assert report["errors"][0]["message"] == "InvalidInput: filename tag combination limit exceeded"


@pytest.mark.parametrize("build", [None, "1"])
def test_compressed_filename_and_metadata_at_boundary(tmp_path, layout, monkeypatch, build):
    monkeypatch.setitem(LIMITS, "tag_combinations", 8)
    wheel = make_wheel(tmp_path, tags="py2.py3-none.abi3-any.linux_x86_64", build=build)
    report = audit([wheel], layout)
    assert report["status"] == "clean", report["errors"]


def test_metadata_real_boundary_counts_duplicate_subtags(tmp_path, layout):
    assert LIMITS["tag_combinations"] == 10000
    tag = ".".join(["py3"] * 100) + "-" + ".".join(["none"] * 100) + "-any"
    wheel = make_wheel(tmp_path, wheel_text=wheel_text(tag))
    report = audit([wheel], layout)
    assert report["status"] == "clean", report["errors"]


@pytest.mark.parametrize("headers, expected", [(2, "clean"), (3, "invalid")])
def test_repeated_headers_share_aggregate_budget(tmp_path, layout, monkeypatch, headers, expected):
    monkeypatch.setitem(LIMITS, "tag_combinations", 8)
    wheel = make_wheel(tmp_path, wheel_text=wheel_text(*(["py3.py3-none.none-any"] * headers)))
    if expected == "invalid":
        monkeypatch.setattr(audit_module, "parse_tag", forbid)
    report = audit([wheel], layout)
    assert report["status"] == expected, report["errors"]
    if expected == "invalid":
        assert report["errors"][0]["message"] == "InvalidInput: WHEEL tag combination limit exceeded"


def test_single_tag_over_boundary(tmp_path, layout, monkeypatch):
    monkeypatch.setitem(LIMITS, "tag_combinations", 8)
    wheel = make_wheel(tmp_path, wheel_text=wheel_text("py3.py3.py3-none.none.none-any"))
    monkeypatch.setattr(audit_module, "parse_tag", forbid)
    report = audit([wheel], layout)
    assert report["errors"][0]["message"] == "InvalidInput: WHEEL tag combination limit exceeded"


@pytest.mark.parametrize("tag", ["py3-none", "py3-none-any-extra"])
def test_malformed_tag_shape_is_invalid_before_expansion(tmp_path, layout, monkeypatch, tag):
    wheel = make_wheel(tmp_path, wheel_text=wheel_text(tag))
    monkeypatch.setattr(audit_module, "parse_tag", forbid)
    report = audit([wheel], layout)
    assert report["status"] == "invalid"
    assert report["errors"][0]["message"] == "InvalidInput: malformed compatibility tag"
