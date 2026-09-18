# Reconciliation and Semantic Evolution

## Goal

Prevent project knowledge from drifting away from code and current intent.

## Change sources

- Agentic Discipline worker;
- human developer;
- external tool;
- dependency update;
- Git merge;
- CI-generated change;
- DB migration;
- config update.

## Reconciliation pipeline

```text
CHANGE DETECTED
→ CLASSIFY CHANGE
→ IMPACT ANALYSIS
→ INVALIDATE STALE CLAIMS/EVIDENCE
→ UPDATE AFFECTED GRAPH REGIONS
→ REVALIDATE INVARIANTS
→ PUBLISH NEW KNOWLEDGE VERSION
```

## Semantic garbage collection

When behavior is retired:
- find linked requirements;
- acceptance;
- tasks;
- tests;
- docs;
- code;
- config;
- decisions.

Assign lifecycle disposition:

```text
KEEP
MIGRATE
DEPRECATE
REMOVE
TEMPORARY
PROMOTE
SUPERSEDED
HISTORICAL
```

## Never silently delete

Deletion requires:
- lifecycle reason;
- scope;
- evidence of replacement/removal;
- re-verification;
- provenance.

## No silent resurrection

Context builder must exclude non-active canonical entities by default.
