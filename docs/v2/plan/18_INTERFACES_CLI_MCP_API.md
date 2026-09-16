# Interfaces: CLI, MCP, API

## CLI first

Initial CLI surface:

```text
agentic adopt .
agentic status
agentic knowledge query ...
agentic discovery status
agentic plan audit
agentic readiness
agentic task list
agentic task claim TASK-123
agentic task checkpoint TASK-123
agentic task resume TASK-123
agentic task block TASK-123
agentic task complete TASK-123
agentic agent join
agentic agent status
agentic evidence list
agentic reconcile
agentic evolution status
agentic context audit TASK-123
agentic doctor
```

## JSON mode

Every command that agents may consume should support machine-readable output.

Example:

```bash
agentic task resume TASK-123 --json
```

## MCP

Expose narrow, composable operations:

- discover_project;
- query_knowledge;
- get_context;
- get_ready_tasks;
- claim_task;
- checkpoint_task;
- release_task;
- resume_task;
- record_discovery;
- record_evidence;
- complete_task;
- impact_analysis;
- reconcile;
- knowledge_health.

## API

Delay until CLI + persistence contracts stabilize.

API should reuse the same application services, not duplicate logic.

## Compatibility

Do not make the internal database schema the public API.
Use versioned DTOs/contracts.
