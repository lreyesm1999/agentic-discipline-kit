# Migration from the pre-public v2.1 payload

This document covers migration from the internal v2.1 milestone to the current public 1.x release.
The command's `3.0` target refers to the internal payload format retained for compatibility; it does
not indicate the public package version.

Run:

```bash
agentic-discipline migrate --to 3.0
```

Migration preserves `AGENTS.md`, `MASTER_PROMPT.md`, `agentic.config.json`, existing acceptance and
specification files, project profiles, and evidence ledgers. It adds the canonical `.agentic/` payload,
an empty verifier registry, and a migration report at `artifacts/migration-v3-report.json`.

The legacy 20 skill paths remain available during the compatibility window. New work can use the
canonical disciplines and verifier commands immediately; no central service is required.
