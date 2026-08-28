# AGENTS.md — Agentic Discipline v2 Orchestrator

## Authority order

1. Explicit human-approved business intent
2. Protected specification
3. Acceptance contract
4. Architecture policy
5. Security policy
6. Quality policy
7. Repository conventions
8. Implementation convenience

Lower levels may not silently override higher levels.

## Workflow state machine

```text
IDEA
→ INTAKE_CAPTURED
→ SPECIFIED
→ ACCEPTANCE_DEFINED
→ ACCEPTANCE_COMPILED
→ PLANNED
→ RISK_CLASSIFIED
→ RED
→ IMPLEMENTING
→ GREEN
→ PROPERTY_VERIFIED
→ REFACTORED
→ CRAP_VERIFIED
→ QUALITY_VERIFIED
→ MUTATION_VERIFIED
→ ARCHITECTURE_VERIFIED
→ SECURITY_VERIFIED
→ INTEGRITY_VERIFIED
→ INDEPENDENTLY_REVIEWED
→ QA_VERIFIED
→ EVIDENCE_FINALIZED
→ RELEASE_READY
→ RETROSPECTIVE_RECORDED
```

## Protected paths

```text
/specs
/acceptance
/architecture
/policies
```

Only a contract-authorized role may change them.

## Conceptual commands

### /init
Detect stack, repository structure, existing tools, CI, test framework, architecture docs, and config.

### /spec <request>
Run:
- 01 Requirements Intake
- 02 Specification
- 03 Acceptance Design
- 04 Acceptance Compiler

### /plan <feature-id>
Run:
- 05 Task Planning
- 06 Risk Classification

### /build <feature-id>
Run:
- 07 Implementation
- 08 Unit Testing
- 09 Property Testing
- 10 Refactoring

### /test <feature-id>
Run:
- 11 CRAP Analysis
- 12 Quality Gates

### /harden <feature-id>
Run:
- 13 Differential Mutation
- 14 Architecture
- 15 Security
- 16 Integrity Audit

### /review <feature-id>
Run:
- 17 Independent Review

### /verify <feature-id>
Run:
- 18 QA
- 19 Release / Evidence

### /retro <feature-id>
Run:
- 20 Agent Retrospective

## Risk profiles

### LOW
Examples:
- copy/text changes
- visual-only adjustment
- isolated non-critical config

Required minimum:
- focused tests
- lint/typecheck/build as applicable
- integrity audit

### STANDARD
Required:
- acceptance
- unit/integration
- coverage
- CRAP/complexity
- architecture
- security
- integrity

### HIGH
Everything in STANDARD plus:
- property tests where meaningful
- differential mutation
- independent review
- black-box QA

### CRITICAL
Everything in HIGH plus:
- full mutation scope for critical modules
- explicit human acceptance
- manual final verification
- no unresolved mutation survivors
- no high/critical security findings
- evidence ledger finalized

## Specification conflict protocol

```text
STATUS: SPEC_CONFLICT
feature: <id>
expected:
observed:
impact:
affected_requirements:
options:
```

Stop that implementation branch.

## Gate tampering protocol

```text
STATUS: QUALITY_GATE_TAMPERING
feature: <id>
evidence:
  file:
  pattern:
  diff:
action:
  revert_bypass
  restore_gate
  rerun_checks
```

## Independent reviewer isolation

The reviewer should receive only:
- specification
- acceptance contract
- architecture policy
- diff
- deterministic evidence

Do not provide the coder's persuasive summary as reviewer context.

## Checkpoints

Recommended git/worktree checkpoints:

```text
checkpoint/spec
checkpoint/red
checkpoint/green
checkpoint/refactored
checkpoint/hardened
checkpoint/release
```

If an autonomous repair loop destabilizes the repository, restore the last known-good checkpoint.

## Evidence standard

Every measurable PASS must have:
- tool name
- command
- exit code
- timestamp
- output artifact
- hash when persisted to ledger

Unknown ≠ PASS.
