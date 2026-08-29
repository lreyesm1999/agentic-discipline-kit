# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 3.x | Yes |
| 2.1.x | Compatibility and migration support only |
| < 2.1 | No |

The current security-supported line is 3.x. Version 2.1 remains available for compatibility while
repositories migrate to the v3 payload, but new security fixes target the current line.

## Reporting a vulnerability

Please do **not** open a public GitHub Issue for a security vulnerability.

Use GitHub's private vulnerability reporting / Security Advisory feature when enabled for the
repository. Include:

- affected version or commit;
- attack or failure scenario;
- reproduction steps;
- impact;
- suggested remediation if known.

Maintainers should acknowledge, triage, remediate, and coordinate disclosure through the private
security channel.

## Scope

Security issues include both conventional software vulnerabilities and framework bypasses that can
cause an AI agent to falsely produce a passing engineering state.
