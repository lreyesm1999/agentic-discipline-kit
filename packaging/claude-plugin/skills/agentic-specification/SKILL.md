---
name: agentic-specification
description: Turns a request into observable behavior with invariants, exclusions and acceptance criteria.
when_to_use: When a request is still expressed as intent rather than behavior, or when material ambiguity would otherwise be resolved silently.
---

# Specification Discipline

Turns a request into observable behavior with invariants, exclusions and acceptance criteria.

**When to use.** When a request is still expressed as intent rather than behavior, or when material ambiguity would otherwise be resolved silently.

Turn a request into observable behavior, invariants, exclusions, and acceptance criteria.

Do not silently resolve material ambiguity; surface it before implementation.

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
