# Failure Injection and Resilience Plan

## Injected failures

### Agent death
Terminate worker mid-task.

Expected:
- lease expires;
- task remains recoverable;
- checkpoint preserved;
- no false completion.

### Context exhaustion
Force early handoff.

Expected:
- context-low mode;
- checkpoint;
- next agent resumes.

### Knowledge write conflict
Two agents edit same entity version.

Expected:
- one commit succeeds;
- one receives conflict;
- no silent overwrite.

### Workspace loss
Delete worktree.

Expected:
- task becomes blocked/recoverable;
- state retained;
- recreation path available.

### Stale evidence
Verify task, then modify relevant code.

Expected:
- evidence becomes stale;
- task may require revalidation.

### External human change
Human edits main branch outside AD.

Expected:
- reconciliation detects diff;
- affected nodes/evidence revalidated.

### Legacy resurrection
Old document mentions removed i18n feature.

Expected:
- historical reference remains queryable;
- active context excludes it;
- no new task is generated to restore it.

### Broken migration
Knowledge DB migration fails halfway.

Expected:
- transaction rollback;
- previous schema remains usable;
- explicit diagnostic.

## Resilience scorecard

For each scenario record:
- detection time;
- recovery path;
- human intervention required;
- data loss;
- duplicated work;
- stale state created.
