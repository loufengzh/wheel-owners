# Related work and scope

Primary sources checked on **2026-10-05**. This is a scope comparison, not a
benchmark, security assessment, or claim that other projects lack undocumented
capabilities. Recheck upstream status before release.

| Project or discussion | Documented focus | Relationship to wheel-owners |
| --- | --- | --- |
| [pip #4625](https://github.com/pypa/pip/issues/4625) | Reports installation overwrites between differently named distributions. The issue was displayed as open. | Establishes the longstanding problem; wheel-owners checks a supplied artifact set before installation. |
| [pip PR #14249](https://github.com/pypa/pip/pull/14249) | Directly related competing work, displayed as open. Its description tracks installed `RECORD` ownership and warns after files have been overwritten. | An upstream installation-time approach. Its behavior and status can change; this project does not replace pip. |
| [`pip check`](https://pip.pypa.io/en/stable/cli/pip_check/) | Checks whether installed packages have compatible declared dependencies. | Dependency consistency is a different question from projected file ownership. wheel-owners performs no dependency resolution. |
| [`check-wheel-contents`](https://github.com/jwodder/check-wheel-contents) | Finds common content and layout mistakes within each wheel, including duplicate content and unexpected top-level entries. | Complementary per-wheel linting. wheel-owners compares projected destinations across the explicitly supplied set. |
| [ModuleGuard paper](https://arxiv.org/abs/2401.02090) and [implementation](https://github.com/ZJU-SEC/ModuleGuard) | Research on ecosystem module conflicts using installation simulation and module extraction. | Important prior work with broader module-conflict research goals. wheel-owners offers a narrowly bounded local path-ownership check, not ecosystem analysis or import reasoning. |
| [SPIRA Trust](https://github.com/snir-spira37/spira-trust) | Offline wheel integrity, evidence, local dependency graph, and policy workflows. | Adjacent local-artifact tooling. wheel-owners focuses on destination ownership and makes no trust or malware verdict. |

## Implementation basis

[PyPA installer](https://installer.pypa.io/en/stable/) supplies wheel installation
abstractions and script generation. wheel-owners pins version `0.7.0` and records
its supported output through a custom destination instead of writing an
installation. The [wheel format specification](https://packaging.python.org/en/latest/specifications/binary-distribution-format/)
explains why archive paths and final installation paths are not always identical.

The useful distinction is the interface and bounded model: explicit local wheels,
explicit layout, generated scripts included, and deterministic JSON. It is not a
claim of unique invention, complete installer equivalence, or superior detection.
