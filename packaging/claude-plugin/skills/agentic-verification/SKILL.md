---
name: agentic-verification
description: Reuses or engineers the smallest deterministic verifier for a measurable claim, with declared pass/fail semantics, dependencies, isolation and sensitivity.
when_to_use: When a claim needs proof, when a verifier may already exist, or before trusting a newly generated verifier.
---

# Verification Engineering

Reuses or engineers the smallest deterministic verifier for a measurable claim, with declared pass/fail semantics, dependencies, isolation and sensitivity.

**When to use.** When a claim needs proof, when a verifier may already exist, or before trusting a newly generated verifier.

For each important claim, classify mechanizability, discover existing verification, and reuse it before generating a verifier. A generated verifier must declare its requirement, pass/fail semantics, dependencies, isolation, and sensitivity method before it can become trusted.

Use `agentic-discipline verifier register`, `verifier validate`, and `verify` for deterministic execution and evidence.

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
