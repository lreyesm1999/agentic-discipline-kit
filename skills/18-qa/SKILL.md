# 18 — QA / Black-Box Verification

## Purpose
Validate observable behavior through the closest real interface.

## Trigger
Engineering gates are green.

## Inputs
- acceptance scenarios
- runnable application/service

## Outputs
- QA results
- regression observations

## Procedure
1. Execute acceptance behavior black-box where practical.
2. Prefer API/UI/CLI boundaries over direct internal calls.
3. Run critical smoke/regression checks.
4. Capture failure evidence.
5. For CRITICAL changes, require explicit manual final verification when policy says so.

## Evidence required
- QA command/procedure and output

## Forbidden
- substituting source inspection for QA

## Stop conditions
- observable behavior differs from acceptance

## Definition of done
- required QA passes
