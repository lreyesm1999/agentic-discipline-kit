# CLI Experience Draft

## Adoption

```bash
agentic adopt .
agentic adopt . --dry-run
agentic adopt . --json
```

## Status

```bash
agentic status
```

Example:

```text
Project: Pharmacy ERP
Knowledge version: 184
Understanding coverage: 87%
Verification coverage: 81%

Ready tasks: 14
Running tasks: 3
Blocked tasks: 2
Agents online: 4
Human decisions: 1
Stale evidence: 6
Stale knowledge: 9
```

## Task flow

```bash
agentic task ready
agentic task claim TASK-142
agentic task context TASK-142
agentic task checkpoint TASK-142
agentic task complete TASK-142
agentic task release TASK-142
agentic task resume TASK-142
```

## Agent flow

```bash
agentic agent join --name cursor-1 --capabilities code,terminal,frontend
agentic agent heartbeat
agentic agent status
```

## Knowledge

```bash
agentic knowledge query "why does refund-service exist?"
agentic knowledge show REQ-102
agentic knowledge history REQ-102
agentic knowledge impact REQ-102
```

## Reconciliation

```bash
agentic reconcile
agentic reconcile --since HEAD~3
```

## Evolution

```bash
agentic evolution status
agentic evolution register REQ-102 --state superseded --reason "Product decision DEC-77"
```
