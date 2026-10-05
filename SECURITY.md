# Security policy

wheel-owners reads potentially untrusted ZIP archives and metadata. It does not
import or execute their package code and does not install their projected files.
Those properties do not make it a sandbox, malware scanner, vulnerability
scanner, or safety certification. A clean ownership report is not a security
verdict. See [the full limits](docs/limits.md).

## Use with untrusted artifacts

- Run without elevated privileges, preferably in an isolated environment with
  operating-system memory, CPU, storage, and time limits.
- Do not make secrets or sensitive files available unnecessarily to the process.
- Keep the tool and its dependencies under version control in your workflow.
  Treat changes to the pinned installer adapter as model changes.
- Treat malformed-input errors, unsupported cases, crashes, and resource-limit
  failures as failed checks, never as evidence that an artifact is safe.
- Review reports before sharing them: artifact names, paths, and metadata can
  disclose details of a private build or environment.

## Reporting a possible vulnerability

Potential issues include unintended filesystem writes, network requests,
execution of package code, path-validation bypasses, and practical denial of
service through archive or metadata parsing.

Use the repository host's private vulnerability-reporting feature if it is
enabled. If there is no private reporting channel, ask a maintainer to provide
one without posting exploit details, sensitive data, or a malicious wheel in a
public issue. This source checkout does not advertise a dedicated security
email address or a guaranteed response time.

Include the tool and Python versions, operating system, minimal reproduction,
expected and observed behavior, and potential impact. Prefer a small synthetic
fixture or a description of how to create it. Do not send credentials or
proprietary wheel contents without arranging an appropriate private channel.

No supported-release window or security-response service level is promised by
this policy. Fixes and support decisions must be stated by the maintainers for
the affected version.
