---
name: agentic-source
description: Establishes the approved intent, constraints and traceability of a change before any edit.
when_to_use: Before editing anything in the repository, and whenever requirements, specs or scope are in question. Stop on specification conflict or unauthorized scope expansion.
---

# Source Discipline

Establishes the approved intent, constraints and traceability of a change before any edit.

**When to use.** Before editing anything in the repository, and whenever requirements, specs or scope are in question. Stop on specification conflict or unauthorized scope expansion.

## Purpose
Protect human intent, constraints, requirements, and traceability.

## [JUDGE]
Identify approved behavior and ambiguity before editing.

## [DISCOVER]
Read relevant specs, contracts, tests, and repository instructions.

## [ENFORCE]
Stop on specification conflict or unauthorized scope expansion.

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
