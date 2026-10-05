# wheel-owners

**Check a local set of Python wheels for overlapping installation paths before installing it.**

[简体中文](docs/README.zh-CN.md) · [Русский](docs/README.ru.md) · [Deutsch](docs/README.de.md)

`wheel-owners` projects the files from explicitly supplied wheels into an explicit
installation layout, then reports shared file ownership and file/directory
conflicts. It uses **PyPA `installer==0.7.0` with a recording-only destination**:
package code is never imported or run, and no projected files are installed.

The question is deliberately small: *would these wheel artifacts claim
incompatible paths under this supported layout?* A clean result is not a promise
that the packages are compatible, importable, trustworthy, or safe.

## Quick start

Requires Python 3.10 or newer on a POSIX host. From this source checkout:

```sh
python -m pip install .
wheel-owners --layout examples/posix-layout.json a.whl b.whl
```

Replace `a.whl` and `b.whl` with actual local wheel filenames. This documentation
does not assume a published PyPI release. Installing the tool can fetch its build
and runtime dependencies; the preflight command itself does not use the network.

Supply every artifact you want checked, including already selected dependencies.
There is no package-name lookup, recursive directory discovery, dependency
resolver, download step, or inspection of your current environment.

## Try a reproducible conflict

The demo generator creates four inert, synthetic wheels in `examples/generated/`:

```sh
python examples/make_demo.py
wheel-owners --layout examples/posix-layout.json \
  examples/generated/alpha-1.0-py3-none-any.whl \
  examples/generated/beta-1.0-py3-none-any.whl
# Exit 1: acme/common.py and the generated acme command have two owners.

wheel-owners --layout examples/posix-layout.json \
  examples/generated/namespace_a-1.0-py3-none-any.whl \
  examples/generated/namespace_b-1.0-py3-none-any.whl
# Exit 0: distinct files in the shared acme namespace directory.
```

## Declare the target layout

The layout is strict JSON. The only supported profile is
`posix-case-sensitive-v1`, and all five scheme paths are required:

```json
{
  "profile": "posix-case-sensitive-v1",
  "interpreter": "/venv/bin/python",
  "scheme": {
    "purelib": "/venv/lib/python3.12/site-packages",
    "platlib": "/venv/lib/python3.12/site-packages",
    "scripts": "/venv/bin",
    "headers": "/venv/include",
    "data": "/venv"
  }
}
```

These are model inputs, not directories the tool creates or probes. Paths must
be absolute, normalized POSIX paths. Use the interpreter path and scheme paths
for your intended installation; the example does not discover them for you.
The interpreter string is used when generating script wrappers, not executed.

Paths are compared exactly by Unicode code point. This profile does not emulate
Windows or macOS case folding, Unicode normalization, symlinks, or a particular
filesystem. Read [the limits](docs/limits.md) before using a result as a gate.

## What counts as a conflict?

- Two owners claim the same projected file path, even if its bytes are identical.
- One projected file path must also be a directory for another projected file.
- Generated console/GUI entry-point scripts collide with other generated scripts,
  raw wheel scripts, or files mapped there by another scheme.
- Different scheme names lead to the same path. For example, `purelib` and
  `platlib` often point at the same `site-packages` directory.

Sharing a directory alone is allowed. Two namespace-package contributors with
distinct files can therefore pass; two copies of a shared `__init__.py` remain
shared file ownership even if they have identical contents. Matching bytes do
not establish exclusive ownership or make a later uninstall safe.

The projection includes supported wheel-root and `.data` placement, raw scripts,
and generated entry-point wrappers. It follows the pinned installer's supported
transformations rather than treating ZIP member names as final destinations.
This is not a simulation of every behavior of pip or another installer.

## Results and automation

The command emits deterministic JSON with `schema_version: 1`. The `status` is
`clean`, `conflict`, or `invalid`. The report includes the chosen `profile` and
`layout`, input `wheels`, projected `claims`, `conflicts`, `errors`, and `limits`.
See [the JSON contract](docs/schema.md). Check the exit code as well as the report:

| Exit | Meaning |
| --- | --- |
| `0` | No ownership conflict found in the supplied, supported model |
| `1` | Ownership conflict found |
| `2` | Invalid input or unsupported case; no clean verdict |

For example, retain the report in CI without losing the command's exit status:

```sh
wheel-owners --layout examples/posix-layout.json a.whl b.whl > ownership.json
```

Malformed wheels and paths, multiple artifacts for the same normalized
distribution name, and unsupported versions or transformations are errors.
Do not treat exit `2`, a missing report, or a failed process as a pass. Select one
artifact per normalized distribution before running the command.

`shared-file` conflicts distinguish identical from different content and include
the affected claims. `file-directory` conflicts identify the blocking file and
descendant claims. If any input fails, the report is `invalid` and its claims and
conflicts are cleared; it does not present a partially checked set as clean.

Determinism is scoped to the same supported inputs, layout, and tool/dependency
versions. Keep the exact wheel artifacts and layout with your build evidence.

## Why another check?

File ownership is a longstanding packaging concern, documented in
[pip issue #4625](https://github.com/pypa/pip/issues/4625). There is also directly
related upstream work in [pip PR #14249](https://github.com/pypa/pip/pull/14249),
which was displayed as open when checked on 2026-10-05. Recheck its status before
making release or positioning claims.

This project makes no claim to have invented conflict detection. Its chosen
interface is an explicit, local wheel-set preflight with a supplied layout and
machine-readable output. See the concise
[comparison and primary sources](docs/comparison.md) for `pip check`,
`check-wheel-contents`, ModuleGuard, SPIRA Trust, and upstream pip work.

## Development

```sh
python -m pip install -e '.[test]'
python -m pytest
python -m build
```

If the build frontend is not installed, install `build` in your development
environment first. See [CONTRIBUTING.md](CONTRIBUTING.md) for scope and review
expectations, [SECURITY.md](SECURITY.md) for reporting guidance, and
[LICENSE](LICENSE) for the MIT license.
