# Migrating an earlier internal payload

This guide is only for teams that used an internal development snapshot before the public 1.x
release. New installations should run `agentic-discipline init` and do not need this command.

The migration target identifies the internal payload format. It is independent of the public package
version:

```bash
agentic-discipline migrate --to 3.0
```

Migration preserves `AGENTS.md`, `MASTER_PROMPT.md`, `agentic.config.json`, existing acceptance and
specification files, project profiles, and evidence ledgers. It installs the canonical `.agentic/`
payload, initializes the verifier registry, and writes
`artifacts/payload-migration-report.json`.

The original 20 workflow skills remain available alongside the canonical disciplines. New work can
use the disciplines and verifier commands immediately; no central service is required.
