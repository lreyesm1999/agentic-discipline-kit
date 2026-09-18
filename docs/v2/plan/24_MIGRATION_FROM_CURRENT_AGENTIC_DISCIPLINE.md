# Migration from Current Agentic Discipline

## Goal

Evolve without throwing away the existing verification and discipline core.

## Preserve first

Do not replace unless evidence proves necessary:
- deterministic verifiers;
- current evidence ledger;
- risk classification;
- protected contracts;
- requirement traceability;
- integrity checks;
- multi-tool agent surfaces;
- stack-aware onboarding.

## Migration strategy

### Step 1 — inventory current artifacts
Classify each as:
- canonical;
- generated;
- project-local;
- compatibility;
- legacy;
- candidate for migration.

### Step 2 — wrap, do not rewrite
Introduce new application services that can consume current artifacts.

### Step 3 — dual-read
During transition:
- old requirement graph remains readable;
- new Knowledge Platform imports and references it.

### Step 4 — dual-write only where necessary
Avoid permanent dual-write.
Use a time-bounded migration window.

### Step 5 — verify parity
For every migrated capability:
- compare old command result;
- compare new command result;
- document intended behavior differences.

### Step 6 — deprecate old paths
Only after:
- migration command exists;
- rollback exists;
- compatibility tests pass.

## Adoption compatibility

Existing repositories should not need to regenerate all project artifacts at once.

Use:
- lazy import;
- incremental indexing;
- ratcheting quality;
- preserved local overrides.
