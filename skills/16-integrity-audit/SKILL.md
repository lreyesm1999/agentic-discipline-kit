# 16 — Integrity / Anti-Gaming Audit

## Purpose
Detect attempts to bypass tests, coverage, lint, mutation, security, or CI.

## Trigger
Every implementation before release.

## Inputs
- git diff
- integrity policy

## Outputs
- tampering report
- suspicious pattern list

## Procedure
1. Run scripts/integrity_audit.py.
2. Inspect new skip/disable/exclusion patterns.
3. Inspect lowered thresholds.
4. Inspect removed assertions and disabled CI steps when detectable.
5. Require justification or revert suspicious bypasses.
6. Emit QUALITY_GATE_TAMPERING for unauthorized bypasses.

## Evidence required
- exact file/line/pattern evidence

## Forbidden
- ignoring suspicious bypass because tests are green

## Stop conditions
- unauthorized tampering detected

## Definition of done
- no blocking integrity finding
