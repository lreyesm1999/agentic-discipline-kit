# Multi-Agent Orchestration

## Key constraint

Agents may come from unrelated subscriptions and tools.

Therefore the system must not depend on one central LLM API.

## Coordination model

Every worker connects to the same control plane.

Conceptual actions:

```text
agent join
agent heartbeat
agent get-ready
agent claim TASK-123
agent checkpoint TASK-123
agent block TASK-123
agent complete TASK-123
agent release TASK-123
agent resume TASK-123
```

## Agent capabilities

Store:

```text
code_editing
terminal
browser
frontend
backend
database
security
testing
documentation
deployment
```

Task claiming may be:
- self-service with compatibility checks;
- orchestrator-assisted;
- human-pinned.

## Leases

Each claimed task gets:

```text
leaseId
taskId
agentId
acquiredAt
expiresAt
heartbeatAt
workspaceId
```

If heartbeat stops:
- lease expires;
- task becomes recoverable;
- latest checkpoint remains;
- another compatible agent may resume.

## Duplicate work prevention

A task with an active valid lease is not claimable unless:
- explicitly shared;
- split into subtasks;
- lease is revoked/expired.

## No direct agent messaging required

Coordination occurs through:
- state;
- checkpoints;
- discoveries;
- evidence;
- task graph;
- integration queue.
