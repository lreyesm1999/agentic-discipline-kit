# 05 — Task Planning

## Purpose
Create vertical slices with explicit traceability and dependency order.

## Trigger
Acceptance is compiled.

## Inputs
- spec
- acceptance IR
- architecture map

## Outputs
- implementation tasks
- affected modules
- test plan

## Procedure
1. Prefer observable vertical slices.
2. Map every task to REQ/AC IDs.
3. Identify migrations/contracts.
4. Predict affected modules.
5. Identify test types required.
6. Avoid orphan tasks.

## Evidence required
- task traceability

## Forbidden
- implementation before risk classification

## Stop conditions
- plan requires unauthorized contract change

## Definition of done
- implementation order is executable and traceable
