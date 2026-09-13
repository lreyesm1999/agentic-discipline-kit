# Test Strategy

## Test pyramid for Agentic Discipline 2.0

### Unit
- IDs;
- state machines;
- precedence;
- lifecycle;
- authority/confidence;
- evidence freshness;
- graph traversal;
- context ranking.

### Contract
- CLI JSON output;
- MCP DTOs;
- persistence repositories;
- schema compatibility.

### Integration
- adoption into fixture repo;
- task claim/checkpoint/resume;
- worktree lifecycle;
- evidence invalidation;
- reconciliation after manual edit.

### End-to-end
Scenario:
1. adopt fixture project;
2. discover;
3. create plan;
4. generate execution graph;
5. claim task;
6. edit;
7. verify;
8. checkpoint;
9. switch agent;
10. resume;
11. complete;
12. reconcile;
13. show console state.

## Critical synthetic repositories

Create fixtures:

```text
fixtures/
  clean-greenfield/
  legacy-docs/
  no-tests/
  broken-tests/
  conflicting-docs/
  stale-code-graph/
  multi-stack/
  schema-migration/
  security-sensitive/
  huge-monorepo-lite/
```

## Required failure tests

- corrupted checkpoint;
- stale lease;
- invalid knowledge version;
- concurrent changeset collision;
- stale evidence;
- manual file edit after verification;
- deleted worktree;
- missing dependency;
- agent crash;
- low-context handoff;
- conflicting requirement;
- legacy docs attempting to reactivate retired feature.

## Property tests

Good candidates:
- completed task always has current evidence;
- active requirement never depends on retired requirement unless explicitly allowed;
- optimistic concurrency never silently drops a write;
- lease ownership is unique;
- rollback restores previous knowledge version.
