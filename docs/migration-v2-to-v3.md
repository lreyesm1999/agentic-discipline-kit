# Migration v2.1 to v3

Run:

```bash
agentic-discipline migrate --to 3.0
```

Migration preserves `AGENTS.md`, `MASTER_PROMPT.md`, `agentic.config.json`, existing acceptance and
specification files, project profiles, and evidence ledgers. It adds the canonical `.agentic/` payload,
an empty verifier registry, and a migration report at `artifacts/migration-v3-report.json`.

The legacy 20 skill paths remain available during the compatibility window. New work can use the
canonical disciplines and verifier commands immediately; no central service is required.
