# Definition of Done v2

A change is DONE only if all required gates for its risk profile are PASS.

Minimum conditions:

1. Requirements are preserved.
2. Requirement graph has no orphan approved requirements.
3. Acceptance contract exists.
4. New/changed behavior was observed red before implementation where feasible.
5. Unit/integration tests pass.
6. Property tests pass when required.
7. Coverage threshold passes.
8. CRAP/complexity threshold passes.
9. Differential mutation passes when required.
10. Architecture checks pass.
11. Security checks pass.
12. Integrity audit reports no unauthorized bypasses.
13. Independent review passes when required.
14. QA verifies observable behavior.
15. Protected paths were not changed without authorization.
16. Evidence ledger contains the final artifacts.
17. Release report says READY TO MERGE: YES.

"Agent says it is correct" is not evidence.
