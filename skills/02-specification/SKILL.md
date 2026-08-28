# 02 — Specification

## Purpose
Create a precise implementation-independent behavioral contract.

## Trigger
Requirements are normalized.

## Inputs
- requirement IDs
- current system behavior

## Outputs
- specs/<feature>.md
- invariants
- failure behavior
- migration behavior

## Procedure
1. Define actors and boundaries.
2. Define MUST/SHOULD/MAY behavior.
3. Define pre/postconditions and invariants.
4. Define failure behavior.
5. Map every section to requirement IDs.

## Evidence required
- complete requirement-to-spec trace

## Forbidden
- implementation details disguised as business requirements

## Stop conditions
- spec contradicts higher-priority approved behavior

## Definition of done
- another agent can implement without hidden context
