# Verification Engineering

Verification Engineering is a core discipline for turning important correctness claims into
reproducible evidence.

1. Extract claims from the approved requirement.
2. Classify each claim as `YES`, `PARTIAL`, or `NO` for mechanization.
3. Discover tests, scripts, CI checks, schemas, and mature tools first.
4. Generate a verifier only when no adequate verifier exists.
5. Prove sensitivity with a baseline RED, known-bad fixture, negative control, mutation, or cross-check.
6. Register and execute the same verifier before and after implementation.

The verifier contract lives in `verifier.json`; normalized results live under
`.agentic/verification/artifacts/` and are hash-linked into the evidence ledger.

`PASS` means the command executed and its declared exit condition passed. `FAIL` means a defined
violation was observed. `UNKNOWN` means the claim was not established. `BLOCKED` means execution could
not complete because of a concrete dependency or environment blocker.
