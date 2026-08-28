# 14 — Architecture Verification

## Purpose
Check executable dependency boundaries and cycles.

## Trigger
Module/layer dependencies changed or architecture gate required.

## Inputs
- architecture policy
- changed dependency graph

## Outputs
- architecture violations report

## Procedure
1. Run configured architecture checker.
2. Detect forbidden direction, cycles, boundary leaks.
3. Compare new edges against policy.
4. Fix violation or request architecture exception.
5. Re-run until clean.

## Evidence required
- checker output
- violation count

## Forbidden
- weakening architecture rules without approval

## Stop conditions
- required architecture change lacks approval

## Definition of done
- zero unapproved violations
