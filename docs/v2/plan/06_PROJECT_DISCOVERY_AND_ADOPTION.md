# Project Discovery and Adoption

## Main command

Conceptually:

```bash
agentic adopt .
```

## Adoption phases

### A. Bootstrap
- identify repository root;
- identify Git status;
- record baseline commit;
- detect existing Agentic Discipline footprint;
- detect existing agent instructions;
- create read-only adoption session.

### B. Discovery
Inspect:
- repository topology;
- stack manifests;
- source directories;
- test directories;
- CI;
- scripts;
- DB schemas/migrations;
- routes/APIs;
- config;
- documentation;
- architecture records;
- current agent rules;
- release artifacts.

### C. Coverage ledger
Track:

```text
Area                  Status       Coverage      Notes
Repository topology   discovered   100%
Source modules        partial      72%
Tests                 discovered   91%
CI/CD                  discovered   100%
Data model             partial      64%
Architecture docs      partial      48%
Runtime behavior       unknown      0%
```

### D. Baseline validation
Run proportionate existing checks:
- build;
- tests;
- lint;
- types;
- schema validation;
- selected smoke tests.

Do not invent commands.

### E. Evidence collection
Record:
- observed stack;
- current failing checks;
- current architecture facts;
- detected features;
- stale docs;
- unresolved conflicts.

### F. Knowledge reconciliation
Classify information as:
- observed;
- declared;
- inferred;
- unknown;
- conflicting;
- deprecated;
- historical.

### G. Canonical baseline
Create a versioned baseline.

### H. Adoption report
Show:
- what was understood;
- what remains unknown;
- current quality baseline;
- stale knowledge;
- blockers;
- recommended next actions.

## Adoption safety

- read-only until plan is generated;
- never inspect secret values;
- never overwrite unmanaged files;
- dry-run all structural changes;
- use transactional apply;
- back up forced changes;
- rollback on partial failure.
