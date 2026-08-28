# 01 — Requirements Intake

## Purpose
Capture informal intent losslessly and normalize it into atomic requirements.

## Trigger
Any new feature, bug fix, behavioral change, or product request.

## Inputs
- original request
- existing requirements
- repository/product constraints

## Outputs
- requirement IDs
- source wording
- assumptions
- conflicts
- out-of-scope

## Procedure
1. Preserve original wording.
2. Create stable IDs: FR-, NFR-, SEC-, ARCH-.
3. Separate fact, assumption, proposal.
4. Detect contradictions.
5. Never silently drop a requirement.
6. Add each requirement to the requirement graph.

## Evidence required
- source-to-requirement mapping

## Forbidden
- production coding
- inventing hidden business rules

## Stop conditions
- irreconcilable contradiction

## Definition of done
- all approved intent is represented by stable IDs
