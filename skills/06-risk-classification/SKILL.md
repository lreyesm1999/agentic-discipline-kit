# 06 — Risk Classification

## Purpose
Classify verification depth from change impact.

## Trigger
Plan exists or a diff exists.

## Inputs
- plan or git diff
- risk policy

## Outputs
- risk score
- LOW/STANDARD/HIGH/CRITICAL
- required gate profile

## Procedure
1. Run deterministic risk_score.py when diff exists.
2. Add semantic risk from plan when not yet coded.
3. Escalate for money/auth/data/security/public-contract changes.
4. Select minimum verification profile.
5. Never downgrade because gates are expensive.

## Evidence required
- risk factors and score

## Forbidden
- confidence-based downgrading

## Stop conditions
- risk cannot be assessed due to missing scope

## Definition of done
- risk profile and required gates are explicit
