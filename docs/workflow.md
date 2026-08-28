# Engineering Workflow

## 1. Intake

Capture the original human request without silently simplifying it. Normalize into stable IDs such as
`FR-001`, `NFR-001`, `SEC-001`, and `ARCH-001`.

## 2. Specification

Write implementation-independent behavior, invariants, failures, authorization rules, and migration
expectations.

## 3. Acceptance

Turn MUST behavior into observable scenarios. New behavior should be demonstrated RED before
implementation when practical.

## 4. Acceptance compilation

Compile acceptance scenarios into a stack-neutral IR. Generated test adapters are disposable;
the protected acceptance contract remains the source of truth.

## 5. Plan and risk

Plan vertical slices and classify the change. Verification depth increases with money, auth,
migration, public API, concurrency, security, architecture, or destructive impact.

## 6. Implement

Implement the smallest coherent slice. A coder may not change protected contracts to make the
implementation pass.

## 7. Test and refactor

Use unit/integration tests, property tests when meaningful, and behavior-preserving refactoring.

## 8. Harden

Run CRAP analysis, configured quality gates, differential mutation, architecture, security, and
integrity checks.

## 9. Independent review

For HIGH/CRITICAL work, review from clean context using contracts, diff, architecture, and evidence.

## 10. QA

Validate behavior through the closest real boundary: API, UI, CLI, message bus, or other external
interface.

## 11. Release

Hash evidence and produce an explicit release decision. UNKNOWN is not PASS.

## 12. Retrospective

Record agent/process failures separately from product truth. Promote recurring lessons into policy
only through explicit review.
