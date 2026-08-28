# 08 — Unit Testing

## Purpose
Protect local decisions, edge cases, and failure modes.

## Trigger
Behavior changes or mutation exposes weak tests.

## Inputs
- changed code
- acceptance behavior

## Outputs
- unit/integration/contract tests as appropriate

## Procedure
1. Test behavior, not private mechanics.
2. Add characterization tests before risky legacy edits.
3. Prefer parameterized tests for input ranges.
4. Verify tests fail for intended reason when feasible.
5. Avoid assertion-free tests.

## Evidence required
- failing and passing test output

## Forbidden
- tautological tests
- deleting assertions

## Stop conditions
- required test implies contract change

## Definition of done
- meaningful local behavior is protected
