# 03 — Acceptance Design

## Purpose
Turn the specification into observable executable-ready scenarios.

## Trigger
Specification is stable.

## Inputs
- spec
- existing acceptance conventions

## Outputs
- AC-* scenarios
- positive/negative/boundary behavior

## Procedure
1. Write observable Given/When/Then behavior.
2. Cover MUST requirements.
3. Add failure and boundary scenarios.
4. Add auth/concurrency/idempotency scenarios when relevant.
5. Map every scenario to requirement IDs.
6. Establish RED baseline before implementation where feasible.

## Evidence required
- requirement-to-AC trace
- red baseline evidence

## Forbidden
- implementation details in acceptance
- weakening existing scenarios

## Stop conditions
- acceptance cannot represent specification

## Definition of done
- all MUST behavior has acceptance coverage
