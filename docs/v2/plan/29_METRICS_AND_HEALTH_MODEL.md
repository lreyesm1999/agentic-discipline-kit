# Metrics and Health Model

## Understanding Coverage
Weighted ratio of required discovery dimensions sufficiently explored for the current scope.

Do not present as scientific precision.

## Traceability Coverage
Percentage of active material requirements linked through expected chain:

```text
Requirement → Acceptance → Task → Code/Test → Evidence
```

## Verification Coverage
Active requirements with current evidence / active requirements requiring evidence.

## Evidence Freshness
Current evidence records / evidence records referenced by active work.

## Knowledge Freshness
Entities not marked stale / active canonical entities.

## Decision Debt
Count of open high-impact decisions that block or constrain execution.

## Execution Flow
- ready;
- running;
- blocked;
- verifying;
- failed;
- completed;
- needs revalidation.

## Context Efficiency
For a task:
- bytes/tokens loaded;
- mandatory context share;
- duplicate content;
- optional history share;
- retrieval hit rate.

## Health rule

Never hide raw counts behind a single "94% healthy" badge.
Every metric should drill down to explainable causes.
