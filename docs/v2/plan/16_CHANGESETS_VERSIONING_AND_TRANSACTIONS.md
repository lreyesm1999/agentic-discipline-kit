# ChangeSets, Versioning, and Transactions

## Why

Multi-agent writes to project knowledge require explicit concurrency control.

## ChangeSet model

```text
changeSetId
title
reason
proposedBy
baseKnowledgeVersion
affectedEntities
affectedEdges
risk
status
```

Statuses:

```text
PROPOSED
VALIDATED
IN_PROGRESS
APPLIED
VERIFIED
ROLLED_BACK
REJECTED
```

## Apply algorithm

1. load base version;
2. compare current entity versions;
3. detect write-write conflicts;
4. run preconditions;
5. run impact analysis;
6. open transaction;
7. apply entity changes;
8. apply edge changes;
9. run invariants;
10. commit;
11. increment knowledge version;
12. emit audit record.

## Conflict behavior

Use optimistic concurrency.

On conflict:
- do not overwrite;
- produce conflict artifact;
- identify competing changes;
- rebase/reconcile;
- retry explicitly.

## Temporal queries

Support future queries such as:
- state at release X;
- decision at time Y;
- requirement version when bug Z existed.

Implement minimally first through versioned records + audit history.
Do not require full event sourcing unless justified.
