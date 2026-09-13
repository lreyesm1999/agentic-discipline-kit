# Plan Intelligence and Readiness

## Purpose

Turn planning from "generate a long plan" into "audit whether a plan is safely executable".

## Input types

- one-sentence request;
- detailed PRD;
- existing backlog;
- technical design;
- partial implementation;
- legacy project;
- mature production system.

## Audit dimensions

- objective clarity;
- scope;
- non-goals;
- acceptance;
- dependencies;
- architecture;
- data;
- API/contracts;
- permissions/security;
- observability;
- rollout/migration;
- failure behavior;
- testing;
- rollback;
- operational ownership;
- unknowns;
- irreversible decisions.

## Result categories

```text
COVERED
PARTIAL
MISSING
CONFLICTING
OBSOLETE
UNKNOWN
```

## Ask-last decision ladder

For every gap:

1. search canonical knowledge;
2. inspect code;
3. inspect tests;
4. inspect current docs;
5. inspect project history;
6. use safe project convention;
7. infer if reversible and low-risk;
8. run experiment;
9. prototype;
10. create a test;
11. external research if authorized;
12. escalate to human.

## Human escalation format

```text
QUESTION
WHY IT BLOCKS
OPTIONS
TRADEOFFS
RECOMMENDATION
SAFE DEFAULT
```

## Readiness result

```text
READY
READY_WITH_MANAGED_UNCERTAINTY
BLOCKED
```

## Readiness gates

Require sufficient confidence in:
- acceptance;
- dependencies;
- verification strategy;
- rollback;
- environment;
- critical architecture constraints;
- human decisions.

Perfect documentation is not required.
Safe autonomous execution is.
