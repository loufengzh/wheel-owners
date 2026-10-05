# Contributing

Keep the project focused: an offline ownership preflight for an explicitly
supplied set of local wheels and an explicit supported layout. Read
[the limits](docs/limits.md) before proposing wider platform or installer support.

## Development setup

Use Python 3.10 or newer on a POSIX host in a virtual environment. From the checkout:

```sh
python -m pip install -e '.[test]'
python -m pytest
```

To build source and wheel distributions, install the `build` frontend if needed
and run:

```sh
python -m build
```

Installing development dependencies can access a package index. Tests and
preflight logic should not require fetching the artifacts being inspected.

## Changes and tests

- Prefer small, reviewable changes with synthetic wheel fixtures. Do not include
  third-party package code merely to reproduce a path collision.
- Include the command, a minimal layout, expected and actual exit codes, and
  relevant JSON in bug reports. Redact local paths or metadata before sharing.
- Add regression tests for every parsing or projection fix. Include invalid
  inputs, same-path and file/directory conflicts, generated and raw scripts,
  scheme aliases, and allowed directory sharing where relevant.
- Preserve order-independent deterministic reporting. Check that reversing the
  wheel input order does not change the logical result.
- Do not import or execute code from a wheel under analysis, install into the
  declared target, add implicit network access, or silently select dependencies.
- Unsupported transformations must produce a clear failure rather than a clean
  result based on a partial projection.

The `installer==0.7.0` pin is part of the model. Updating it requires reviewing
the adapter and script generation, adding differential/regression coverage, and
updating the documented scope. Changes to the JSON contract or path profile
likewise need explicit versioning review. Keep translated READMEs aligned with
the English contract.

## Documentation and release checks

Use precise claims and primary-source links. Do not claim complete filesystem
emulation, guaranteed security, or that conflict detection is a new invention.
Recheck the dated upstream status in [comparison.md](docs/comparison.md) before
release. Verify example commands against the implementation and run the full
test suite and package build before proposing a release.

For a possible vulnerability, follow [SECURITY.md](SECURITY.md) rather than
posting sensitive details or a weaponized archive publicly.
