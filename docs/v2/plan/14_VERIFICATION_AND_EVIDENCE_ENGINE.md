# Verification and Evidence Engine

## Evidence types

- unit;
- integration;
- E2E;
- build;
- lint;
- typecheck;
- schema validation;
- contract tests;
- database assertions;
- runtime observation;
- security scans;
- architecture checks;
- performance benchmarks;
- screenshots;
- logs;
- browser traces.

## Evidence record

Each record should include:

```text
evidenceId
claimOrRequirement
tool
command
environment
startedAt
finishedAt
exitCode
result
artifactRefs
codeVersion
knowledgeVersion
sensitivity
scope
```

## Evidence currency

Historical PASS != current proof.

Invalidate or downgrade evidence when:
- relevant implementation changes;
- requirement changes;
- verifier changes;
- dependency changes affect semantics;
- test fixtures become stale;
- protected metadata changes.

## Completion gate

A task cannot become completed unless:
- all required evidence types exist;
- all blocking evidence is PASS;
- no required evidence is stale;
- protected contracts remain valid.

## Evidence ledger

Maintain append-only audit capability.

At minimum:
- sequential ID;
- previous hash;
- record hash;
- artifact hashes.

The ledger is audit evidence, not a substitute for meaningful test design.
