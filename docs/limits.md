# Limits and interpretation

A clean report means only that the supplied artifacts did not produce an
ownership conflict in the supported projection. Read this together with the
[README](../README.md); these limits are part of the result's meaning.

## Input boundary

- Only explicitly named local wheel files are considered. Dependencies not in
  that set are invisible, even if required by metadata.
- No package index, resolver, lockfile resolution, source-distribution build, or
  editable-install behavior is modeled.
- Only one artifact per normalized distribution name is accepted. Alternative
  versions or platform builds are not interpreted as candidates to choose among.
- Input validation rejects malformed or unsupported cases rather than promising
  to handle the full range of wheels accepted by other installers.

The current format subset requires `Wheel-Version: 1.0` and supports metadata
versions through `2.4`, ordinary single-disk ZIP STORE/DEFLATE compression, and SHA-256, SHA-384, or
SHA-512 `RECORD` hashes. The archive and `RECORD` file sets must agree and hashes
must validate. Wheel signatures, ZIP64, and prepended/trailing archive data are unsupported. These consistency checks do
not authenticate the publisher or prove the absence of malicious content.

The parser also has fixed limits:

| Input | Limit |
| --- | --- |
| Explicit wheel artifacts | 64 |
| Archive file or individual expanded member | 64 MiB |
| Archive bytes across the entire set | 256 MiB |
| Expanded content per wheel / entire set | 256 MiB / 512 MiB |
| Archive entries per wheel / entire set | 10,000 / 20,000 |
| Individual `.dist-info` member | 2 MiB |
| Layout JSON | 16 KiB |
| Path / path component (UTF-8) | 4,096 bytes / 255 bytes |
| Components per path | 64 |
| Serialized JSON report (including final newline) | 16 MiB |
| Claim references across report/conflicts | 50,000 |

Generated console/GUI commands count toward the entry limits as well.
The central-directory count and record boundaries are checked before constructing
ZIP member objects; declared expanded sizes are charged before decompression.
A reference budget is charged before adding conflict evidence, and a streaming
JSON size check rejects oversized reports before building the complete JSON
string. Exceeding either report budget produces `invalid`, with no partial
claims or conflicts.

These bounds constrain supported inputs; they are not a security-sandbox or
worst-case resource guarantee. Exceeding a limit prevents a clean verdict.

## Installation model

The adapter is pinned to PyPA `installer==0.7.0` and must run on a POSIX host.
Supported wheel files are
projected through a recording-only destination. Wheel root files and `.data`
scheme placement, generated POSIX entry-point wrappers, and raw scripts are
included in the supported model. The supplied interpreter path influences script
generation; it is not checked for existence or executed.

No target directory is installed into or examined. In particular, the check
cannot find conflicts with packages already installed, unmanaged files, system
commands, or a previous version of a package. The model is not a dry run of pip,
and installer-specific extra metadata or transformations outside the supported
adapter are not guaranteed to match a later installation.

Bytecode generation is not modeled. `.pth` files are considered only as file
payloads: their effects on `sys.path`, executable lines, and import hooks are not
evaluated. Package imports and entry-point targets are never executed.

## Path semantics

The sole profile is `posix-case-sensitive-v1`. All scheme paths and the
interpreter path must be absolute, normalized POSIX paths. Scheme roots may
alias each other; the final projected paths are compared rather than assuming
each scheme has separate storage.

Path equality is **exact Unicode-code-point equality**. There is no Unicode
normalization or confusable analysis, no Windows or macOS case-fold simulation,
and no claim of actual filesystem fidelity. Symlink resolution, hard links,
mounts, permissions, filesystem encodings, path-length limits, and existing
directory topology are outside the model. Even a filesystem described as
case-sensitive may have behavior this profile does not represent.

Directory sharing alone is permitted. This supports ordinary namespace-package
layouts at the path level; it does not prove namespace import behavior. A file
that is also needed as an ancestor directory is a conflict. Multiple claims on
one file are conflicts even when their bytes match. There is no allowlist that
turns identical bytes into exclusive ownership.

## What the result does not establish

- Dependency, Python-version, ABI, platform, or runtime compatibility
- Import resolution, module shadowing at different paths, or runtime correctness
- Malware absence, package provenance, vulnerability status, or security
- Correct behavior of installation, upgrade, or uninstall in a real environment
- Completeness of the selected artifact set or correctness of its resolution

The parser processes untrusted archives. Avoid elevated privileges; use an
isolated, resource-limited environment for untrusted inputs. Static inspection
is not a security sandbox or a security guarantee.

## Automation and change control

Exit `0` is a bounded clean result; exit `1` records conflicts; exit `2` denotes
invalid or unsupported input. Any input error makes the whole report `invalid`
and clears projected claims and conflicts, rather than presenting partial
coverage as a clean set. Preserve these distinctions. A process crash,
resource-limit failure, or missing output is not a clean result.

Preserve exact wheels, the layout JSON, the report, and tool/dependency versions
when comparing runs. A change to the adapter, installer version, layout profile,
or JSON contract needs explicit review and regression tests. Do not generalize
results from this profile to an unsupported platform.
