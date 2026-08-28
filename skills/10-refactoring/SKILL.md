# 10 — Refactoring

## Purpose
Reduce complexity/coupling after behavior is green.

## Trigger
Tests are GREEN.

## Inputs
- changed modules
- complexity/duplication evidence

## Outputs
- behavior-preserving structural improvements

## Procedure
1. Capture green baseline.
2. Identify structural hotspots.
3. Refactor in small steps.
4. Run focused tests after each step.
5. Re-run acceptance.
6. Stop when thresholds pass; avoid endless beautification.

## Evidence required
- before/after metrics
- green tests

## Forbidden
- changing behavior under refactor label

## Stop conditions
- behavior changes unexpectedly

## Definition of done
- structure improves without behavioral regression
