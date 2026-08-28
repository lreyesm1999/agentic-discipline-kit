# 20 — Agent Retrospective

## Purpose
Learn from workflow failures without modifying business truth.

## Trigger
After failed loops, review findings, gate tampering, rollback, or completed high-risk work.

## Inputs
- failure/review history
- evidence
- agent actions

## Outputs
- retrospective record
- candidate workflow rule
- recurring-pattern count

## Procedure
1. Identify what the agent/process did wrong or inefficiently.
2. Separate one-off incident from recurring pattern.
3. Record cause, detection signal, corrective rule, and scope.
4. Store in `.agent-memory/failures.jsonl`.
5. Do not auto-change protected business contracts.
6. Promote recurring workflow rules only through explicit policy update.

## Evidence required
- failure entry with evidence reference

## Forbidden
- rewriting product requirements based on agent mistakes

## Stop conditions
- evidence insufficient to infer cause

## Definition of done
- retrospective is recorded and actionable
