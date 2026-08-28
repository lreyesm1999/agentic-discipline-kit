# 09 — Property Testing

## Purpose
Verify invariants over broad generated input spaces.

## Trigger
HIGH/CRITICAL risk or logic with meaningful invariants.

## Inputs
- invariants
- changed pure/business logic

## Outputs
- property tests
- generated counterexample evidence

## Procedure
1. Extract algebraic/domain invariants.
2. Use stack tool:
   TS: fast-check
   Python: Hypothesis
   .NET: FsCheck
3. Define generators and shrinking strategy.
4. Run properties.
5. Turn discovered counterexamples into regression tests where useful.

## Evidence required
- property execution output
- counterexamples

## Forbidden
- meaningless random tests
- unstable non-deterministic generators

## Stop conditions
- no valid property can be stated

## Definition of done
- required properties pass
