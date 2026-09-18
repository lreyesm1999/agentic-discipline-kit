# Task Contracts and Execution Graph

## Task contract

Every executable task must include:

```text
ID
Objective
Scope
Out of scope
Requirement links
Acceptance criteria
Dependencies
Affected boundaries
Required context
Test strategy
Required evidence
Rollback
Definition of done
Risk profile
Autonomy budget
```

## Vertical slice preference

Prefer tasks that deliver or prove coherent behavior end-to-end.

Bad:
- build repositories;
- build controllers;
- build DTOs;
- later build tests.

Better:
- implement product search end-to-end;
- implement order cancellation end-to-end;
- implement inventory adjustment end-to-end.

## Execution states

Recommended minimum:

```text
PLANNED
READY
CLAIMED
RUNNING
BLOCKED
VERIFYING
FAILED
COMPLETED
SUPERSEDED
CANCELLED
NEEDS_REVALIDATION
```

## State transition examples

```text
PLANNED → READY
READY → CLAIMED
CLAIMED → RUNNING
RUNNING → VERIFYING
VERIFYING → COMPLETED
VERIFYING → FAILED
RUNNING → BLOCKED
FAILED → READY
COMPLETED → NEEDS_REVALIDATION
```

## Completion invariant

`COMPLETED` requires:
- all acceptance criteria satisfied;
- required evidence present;
- evidence current for code/knowledge version;
- no unresolved blocking invariant;
- integration gate passed if parallel work was involved.
