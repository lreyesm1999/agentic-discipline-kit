# Project Console and Human UX

## Core views

### Overview
Show:
- project health;
- knowledge health;
- ready tasks;
- running agents;
- blocked tasks;
- stale knowledge;
- unresolved human decisions.

### Features / Requirements
Show:
- status;
- acceptance;
- implementation links;
- verification;
- evidence freshness.

### Execution
Show:
- task graph;
- running leases;
- blocked dependencies;
- integration queue.

### Agents
Show:
- agent identity;
- capability profile;
- current task;
- lease expiry;
- last heartbeat.

### Evidence
Show:
- claim;
- verifier/test;
- result;
- code version;
- freshness.

### Decisions
Show:
- accepted;
- assumed;
- open;
- rejected;
- revisit condition.

### Evolution
Show:
- deprecated;
- temporary;
- migration-required;
- removal candidates;
- unresolved cleanup.

## Human decisions queue

Each decision card:

```text
Question
Why this blocks
Options
Tradeoffs
System recommendation
Safe default
Affected tasks
```

## Health metrics

Suggested:
- understanding coverage;
- traceability coverage;
- verification coverage;
- evidence freshness;
- stale knowledge count;
- unresolved conflicts;
- blocked critical tasks;
- current human blockers.

Avoid vanity percentages.
Metrics must be explainable.
