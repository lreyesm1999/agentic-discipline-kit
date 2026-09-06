---
description: Apply property, mutation, security and integrity pressure.
argument-hint: '[path or area]'
---

# /harden

Apply property, mutation, security and integrity pressure.

## Steps

1. Apply **Hardening Discipline** (`agentic-hardening`): Applies property tests, mutation, security, integrity and negative controls without weakening any gate.
2. Apply **Architecture Discipline** (`agentic-architecture`): Protects dependency direction, module boundaries and structural invariants, preferring existing analyzers over new ones.

## Stop conditions

1. Human-approved intent and protected contracts outrank convenience.
2. Understand the relevant source, tests, contracts, and commands before changing code.
3. Preserve approved behavior and make the smallest coherent change.
4. Reuse an existing adequate verifier before generating one.
5. If a measurable claim lacks a verifier, engineer the smallest deterministic verifier and prove its sensitivity.
6. Evidence comes from execution; `UNKNOWN` and `BLOCKED` are never `PASS`.
7. Never weaken gates, thresholds, fixtures, or verifier semantics to obtain green.
8. Every replacement, temporary artifact, fallback, test, and verifier needs an explicit lifecycle disposition.
9. Cleanup is followed by re-verification.

Report `UNKNOWN` or `BLOCKED` rather than presenting an unproven claim as `PASS`.
