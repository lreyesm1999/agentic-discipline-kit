# Workspaces, Parallelism, and Integration

## Workspace isolation

Recommended:
- Git worktrees for local multi-agent use;
- separate branches;
- optional container/sandbox for risky tooling.

Never allow multiple agents to edit the same mutable working tree by default.

## Parallel safety classifier

Before parallelization, inspect overlap across:

- files;
- modules;
- schemas;
- migrations;
- public contracts;
- generated files;
- shared dependencies;
- config;
- architecture boundaries.

Classify:

```text
SAFE_PARALLEL
PARALLEL_WITH_REVIEW
SERIALIZE
CONFLICTING
```

## Semantic conflict examples

Git may report no text conflict while behavior conflicts.

Examples:
- two agents modify the same API contract in different files;
- two migrations assume the same schema baseline;
- two features alter the same business invariant.

## Integration gate

Before merging:
1. refresh target baseline;
2. compare knowledge version;
3. rebase/merge branch;
4. detect changed assumptions;
5. run task tests;
6. run cross-task integration tests;
7. validate protected contracts;
8. validate knowledge invariants;
9. verify evidence currency;
10. merge;
11. update canonical knowledge;
12. close task.
