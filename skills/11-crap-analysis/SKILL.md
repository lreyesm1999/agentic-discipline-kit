# 11 — CRAP Analysis

## Purpose
Combine complexity and coverage to find risky changed functions/modules.

## Trigger
Changed code is green and coverage data exists.

## Inputs
- coverage artifact
- complexity artifact
- changed symbols

## Outputs
- CRAP report
- max CRAP
- hotspots

## Procedure
1. Parse per-function complexity and coverage when supported.
2. Compute CRAP = CC^2 * (1 - coverage)^3 + CC.
3. Focus on changed functions first.
4. Fail when configured max is exceeded.
5. Recommend test improvement or simplification, not threshold weakening.

## Evidence required
- CRAP inputs and computed values

## Forbidden
- guessed complexity/coverage

## Stop conditions
- required input artifacts unavailable

## Definition of done
- changed code satisfies configured CRAP threshold
