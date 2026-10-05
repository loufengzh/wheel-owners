# Verification evidence

Local checks on 2026-10-05 used Linux, Python 3.12.14, PyPA installer 0.7.0,
packaging 26.0, pytest 8.4.2, and build 1.6.1. Build isolation selected
setuptools 82.0.1. These are observed local results, not a claim that hosted CI
has run or that every supported Python version has been exercised locally.

## Reproduce

```sh
python -m pip install -e '.[test]'
python -m pytest -q
python -m build
python examples/make_demo.py
```

The local suite passed **101 tests**, including **10 differential cases**:

- Eight combinations of pure/platlib root, aliased/separate library schemes, and
  plain/space-containing interpreter paths compare against actual installer
  output. They compare every output destination, SHA-256, byte size, and
  executable flag, including generated console/GUI scripts, rewritten raw
  scripts, all five `.data` schemes, and regenerated RECORD.
- The required alpha/beta overlap is independently reproduced by installing each
  inert wheel into a separate temporary directory. The intersection of actual
  destinations exactly equals the two reported paths: `acme/common.py` and the
  generated `acme` command.
- Separate `acme/a.py` and `acme/b.py` namespace contributors actually install
  together into a temporary target and exactly match a clean projection.

Only the differential test harness performs real installation writes, under pytest temporary
directories. It disables bytecode and never imports or executes fixture package
code. The production audit uses a recording-only destination and never invokes
that test harness.

Other tests cover argument-order determinism, identical-byte ownership,
intra-wheel aliases, generated/raw command overlaps, ancestor-file conflicts,
normalized duplicate distributions, malformed metadata/RECORD/paths, unsupported
signatures, input resource budgets, generated-command budgets, symlinks, FIFO
rejection without blocking, deep JSON, central-directory count manipulation, ZIP64 and per-member multi-disk flags,
raw metadata header interpretation, report amplification budgets,
Unicode code-point equality, and all three CLI exit codes.

## Package and demo checks

- Source distribution and wheel built successfully.
- Built wheel installed into a fresh virtual environment. From outside the
  checkout, imports resolved to that environment's `site-packages` and
  `wheel-owners --version` returned `0.1.0`.
- `pip check` found no broken requirements in the fresh environment.
- The installed wheel produced byte-for-byte identical JSON to the source CLI
  for both demos: conflict exit 1 with 12 claims/two conflicts; clean exit 0 with
  eight claims/no conflicts.
- The tool's own built wheel passed a single-artifact ownership preflight.
- Chinese, Russian, German, and English layout examples and relative links were
  checked. The primary-source comparison was reviewed separately from core code.

Committed `examples/conflict-report.json` and `examples/clean-report.json` are
reproducible demo outputs, not third-party package findings. The generator uses
fixed ZIP metadata so its artifacts are repeatable.

The GitHub Actions workflow is configured for Python 3.10–3.14 on Ubuntu, runs
the tests, builds both distributions, and smoke-installs the built wheel. Hosted
workflow results must be checked for the exact published commit before claiming
CI is green. Independent review and publication are separate release steps.

Independent adversarial review found two validation-contract gaps (encoded WHEEL
scalar interpretation and local ZIP64 detection) and report-size amplification.
The fixes now use the pinned installer's raw header parsing semantics, inspect
both local and central ZIP records, and enforce reference/serialized-report
budgets. Dedicated regressions are included. Four additional reviewer-generated
actual-installer comparisons also matched exactly; they supplemented, rather
than replaced, the committed suite.
