"""Small JSON-only CLI; stdout always holds a report except --help/--version."""
from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .audit import audit, invalid_report, load_layout


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def main(argv=None) -> int:
    parser = Parser(description="Offline ownership preflight for explicit local wheels and a POSIX layout")
    parser.add_argument("--version", action="version", version=f"wheel-owners {__version__}")
    parser.add_argument("--layout", required=True, help="explicit POSIX target layout JSON")
    parser.add_argument("wheels", nargs="+", help="explicit local .whl files (already resolved)")
    try:
        args = parser.parse_args(argv)
        report = audit(args.wheels, load_layout(args.layout))
    except Exception as exc:
        report = invalid_report(f"{type(exc).__name__}: {exc}")
    try:
        print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    except BrokenPipeError:
        return 2
    return {"clean": 0, "conflict": 1, "invalid": 2}[report["status"]]


if __name__ == "__main__":
    sys.exit(main())
