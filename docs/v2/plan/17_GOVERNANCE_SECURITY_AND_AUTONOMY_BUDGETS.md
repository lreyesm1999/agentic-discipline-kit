# Governance, Security, and Autonomy Budgets

## Permission scopes

Possible scopes:
- repository read;
- repository write;
- specific path write;
- test execution;
- local database;
- network;
- external service;
- deployment;
- production;
- destructive command.

## Protected actions

Human approval by default for:
- production deployment;
- secret rotation;
- destructive DB operations;
- account/permission changes;
- irreversible external writes;
- regulated workflow changes;
- high-value financial behavior.

## Secrets

Do not persist:
- API keys;
- passwords;
- tokens;
- private certificates;
- `.env` values;
- sensitive production data.

Persist:
- key name;
- required presence;
- source/provider;
- secret reference.

## Autonomy budgets

Per task or policy profile:

```text
maxRuntime
maxRetries
maxFilesChanged
maxLinesChanged
maxBlastRadius
maxExternalCalls
maxCost
allowedCommands
allowedPaths
allowedEnvironments
```

When exceeded:
- checkpoint;
- stabilize;
- mark blocked or needs-review;
- provide evidence and next action.

## Authority precedence

Recommended configurable hierarchy:

```text
explicit current human decision
> protected current contract
> verified runtime/test evidence
> current code/config
> current docs
> historical docs
> agent inference
```

Use domain-specific exceptions where needed.
