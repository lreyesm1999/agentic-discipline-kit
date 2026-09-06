---
name: agentic-qa
description: Validates user-visible behavior independently from implementation assumptions.
when_to_use: Before release, and for any material change needing regression or black-box scenarios.
---

# QA Discipline

Validates user-visible behavior independently from implementation assumptions.

**When to use.** Before release, and for any material change needing regression or black-box scenarios.

Validate user-visible behavior independently from implementation assumptions, including regression and black-box scenarios for material changes.

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
