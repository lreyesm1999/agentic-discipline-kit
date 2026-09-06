---
name: agentic-evidence
description: Normalizes executed statuses, commands, exit codes, artifact hashes and provenance into a release record.
when_to_use: When recording or verifying results for a release decision, or when a PASS is being claimed without execution.
---

# Evidence Discipline

Normalizes executed statuses, commands, exit codes, artifact hashes and provenance into a release record.

**When to use.** When recording or verifying results for a release decision, or when a PASS is being claimed without execution.

Normalize executed results, statuses, commands, exit codes, artifact hashes, and provenance. Narrative confidence cannot create a PASS.

## Non-negotiables

1. Human-approved intent and protected contracts outrank convenience.
2. Understand the relevant source, tests, contracts, and commands before changing code.
3. Preserve approved behavior and make the smallest coherent change.
4. Reuse an existing adequate verifier before generating one.
5. If a measurable claim lacks a verifier, engineer the smallest deterministic verifier and prove its sensitivity.
6. Evidence comes from execution; `UNKNOWN` and `BLOCKED` are never `PASS`.
7. Never weaken gates, thresholds, fixtures, or verifier semantics to obtain green.
8. Every replacement, temporary artifact, fallback, test, and verifier needs an explicit lifecycle disposition.
9. Cleanup is followed by re-verification.

## Deterministic checks

Measurable claims are proved by execution, not narration. When the CLI is available:

```bash
agentic-discipline quality --config agentic.config.json
agentic-discipline verify <VERIFIER-ID>
```
