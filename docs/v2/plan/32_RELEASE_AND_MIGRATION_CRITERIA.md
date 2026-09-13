# Release and Migration Criteria

## Alpha
Must demonstrate:
- local persistence;
- project adoption;
- knowledge baseline;
- plan audit;
- execution graph;
- checkpoint/resume.

## Beta
Must demonstrate:
- multi-agent leases;
- worktree isolation;
- evidence freshness;
- reconciliation;
- lifecycle cleanup;
- MCP.

## RC
Must demonstrate:
- console;
- governance;
- failure injection;
- migration from current Agentic Discipline;
- performance baseline;
- documented limitations.

## Stable 2.0
Must pass:
- project adoption E2E;
- cross-agent continuity E2E;
- multi-agent parallel integration E2E;
- stale evidence invalidation E2E;
- legacy resurrection prevention E2E;
- external manual change reconciliation E2E;
- rollback/migration tests;
- security threat tests.

## Migration promise

Existing current-version users should have:
- explicit migration command;
- dry-run;
- no silent overwrite;
- backup of forced changes;
- rollback guide.
