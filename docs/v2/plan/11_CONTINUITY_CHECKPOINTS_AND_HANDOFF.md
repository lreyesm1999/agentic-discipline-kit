# Continuity, Checkpoints, and Handoff

## Goal

A replacement agent should continue from project state, not from chat archaeology.

## Checkpoint payload

Required:

```text
taskId
objective
executionPhase
completedWork
modifiedFiles
commandsRun
testsRun
testResults
failures
discoveries
assumptions
pendingIssues
currentHypothesis
nextAction
branch
workspace
commitSha
knowledgeVersion
evidenceRefs
timestamp
```

## Checkpoint triggers

- task start;
- meaningful implementation milestone;
- test run;
- significant failure;
- fix validated;
- architecture discovery;
- before risky operation;
- before handoff;
- session termination;
- context-low.

Do not checkpoint every keystroke.

## Resume flow

```text
agent joins
→ requests TASK-287
→ obtains latest valid checkpoint
→ verifies workspace/branch
→ verifies baseline has not changed incompatibly
→ refreshes minimum context
→ continues
```

## Handoff format

The handoff must distinguish:
- completed;
- proposed;
- failed;
- blocked;
- unverified.

It must not:
- include secrets;
- claim passing checks without execution evidence;
- paste huge logs when a durable artifact reference exists.
