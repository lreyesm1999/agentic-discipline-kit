# Discovery Coverage and Graph-First Navigation

## Goal

Prevent the agent from claiming "I studied the repository" after sampling only a fraction.

## Coverage ledger dimensions

- repository topology;
- source code;
- test code;
- docs;
- CI/CD;
- config;
- build scripts;
- persistence;
- APIs;
- runtime entrypoints;
- infrastructure;
- agent instructions.

## Coverage states

```text
NOT_STARTED
PARTIAL
SUFFICIENT
EXHAUSTIVE
NOT_APPLICABLE
STALE
```

## Graph-first discovery rule

Use:

```text
graph neighborhood
→ source confirmation
→ runtime/test confirmation where relevant
```

Never:

```text
graph says X
→ assume X is true
```

## Staleness rule

If graph and source disagree:
- source wins for implementation structure;
- mark graph node/edge stale;
- trigger incremental reindex.

## Query discipline

- start narrow;
- widen only when evidence is missing;
- avoid whole-repo scans when a symbol neighborhood is enough;
- fetch decisive source before edits;
- preserve exact file/symbol references.

## Discovery completeness is task-relative

For a frontend CSS fix, full DB understanding is not required.

For a schema migration, DB + API + persistence + affected tests may be mandatory.

The Context Engine should request the coverage needed by the task, not a universal 100%.
