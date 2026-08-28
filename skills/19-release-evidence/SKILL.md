# 19 — Release & Evidence Ledger

## Purpose
Aggregate evidence, hash artifacts, and make an explicit release decision.

## Trigger
All required gates for the risk profile have completed.

## Inputs
- gate artifacts
- QA
- review
- protected-path result

## Outputs
- release report
- ledger entries
- READY TO MERGE decision

## Procedure
1. Ensure required evidence exists.
2. Hash persisted artifacts.
3. Append them to evidence ledger.
4. Verify no required status is UNKNOWN/FAIL.
5. Produce compact release report.
6. READY TO MERGE only when all required gates pass.

## Evidence required
- evidence hashes
- ledger sequence

## Forbidden
- declaring release-ready with missing evidence

## Stop conditions
- any required gate failed/unknown

## Definition of done
- final release report is evidence-backed
