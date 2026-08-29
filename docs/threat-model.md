# Threat model

Generated verifiers are executable code, not trusted prose. The runtime therefore:

- validates metadata against `schemas/verifier.schema.json`;
- restricts working directories to the project or verifier package;
- reports missing dependencies as `BLOCKED`;
- captures command, exit code, timing, environment, and hashes;
- requires sensitivity evidence before protection;
- detects changes to protected verifier metadata;
- never converts an unavailable execution into `PASS`.

Destructive or production-targeting verification remains an explicit project decision. Prefer fixtures,
temporary directories, disposable databases, and mature external tools.
