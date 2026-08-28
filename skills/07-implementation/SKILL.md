# 07 — Implementation

## Purpose
Implement the smallest correct slice without changing protected contracts.

## Trigger
Plan + risk classification + RED acceptance exist.

## Inputs
- target task
- protected spec
- acceptance IR/tests

## Outputs
- production code
- migrations/config as required

## Procedure
1. Confirm target acceptance is RED.
2. Implement one coherent slice.
3. Run focused tests.
4. Keep protected paths untouched.
5. Emit SPEC_CONFLICT instead of coding around contradictions.
6. Stop unrelated refactoring until behavior is GREEN.

## Evidence required
- red→green evidence

## Forbidden
- protected-contract edits
- disabling gates

## Stop conditions
- spec conflict
- tool blocker

## Definition of done
- target behavior is GREEN
