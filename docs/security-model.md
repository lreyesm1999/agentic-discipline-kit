# Security Model

The framework assumes an AI coding agent may be competent but untrusted.

## Threats considered

- weakening tests
- adding test skips
- disabling coverage
- suppressing type/lint warnings
- adding scanner exclusions
- editing acceptance contracts after implementation
- changing architecture rules to fit code
- reporting invented metrics
- hiding relevant failures in summaries

## Controls

- protected paths
- deterministic evidence
- integrity scanner
- independent review
- evidence hashes
- CI enforcement
- risk-sensitive verification depth

This is defense in depth. It does not replace repository permissions, branch protection, secret
management, dependency security, or human governance.
## Trusted configuration boundary

`agentic.config.json` contains executable commands. The engine executes argument vectors directly
without a shell; string commands are parsed for backward compatibility, while JSON arrays are the
recommended unambiguous form. Treat configuration changes as executable-code changes: review them,
protect the branch, and never consume an untrusted external configuration file.
