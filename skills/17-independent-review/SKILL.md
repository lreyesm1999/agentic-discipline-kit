# 17 — Independent Review

## Purpose
Adversarially review the change without implementer anchoring.

## Trigger
HIGH/CRITICAL risk or configured review requirement.

## Inputs
- spec
- acceptance
- architecture
- diff
- deterministic evidence

## Outputs
- independent findings
- PASS/FAIL

## Procedure
1. Reconstruct intent from contracts first.
2. Inspect diff second.
3. Look for missing behavior, scope drift, weak failure handling, unsafe defaults, race conditions.
4. Cross-check every quality claim against evidence.
5. Attempt to identify plausible failure modes.
6. Return blocking/non-blocking findings.

## Evidence required
- reviewed diff range
- referenced evidence

## Forbidden
- trusting coder summary as proof

## Stop conditions
- evidence bundle incomplete

## Definition of done
- no unresolved blocking finding
