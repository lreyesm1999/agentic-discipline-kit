# 13 — Differential Mutation Testing

## Purpose
Challenge tests only where the change creates mutation risk.

## Trigger
HIGH/CRITICAL risk or configured mutation gate.

## Inputs
- git diff
- changed modules
- mutation tool

## Outputs
- mutation score
- survivors
- survivor triage

## Procedure
1. Compute changed production modules.
2. Target mutation tool to changed modules where supported.
3. Classify survivors: weak test, dead code, equivalent, tooling issue.
4. Strengthen tests or simplify code.
5. Require zero critical survivors.
6. Document explicit equivalent mutants.

## Evidence required
- mutation report
- survivor disposition

## Forbidden
- exclusions solely to improve score

## Stop conditions
- tool cannot target relevant code
- survivor reveals spec ambiguity

## Definition of done
- threshold passes and no untriaged critical survivor remains
