# Phase-by-Phase Hyperdetailed Plan


## P00 — Current System Audit

### Objective
Map exactly what current Agentic Discipline already solves; avoid rebuilding working capabilities.

### Preconditions
- Prior dependency phases are verified.
- Current branch/workspace is clean or unrelated work is preserved.
- Relevant architectural decisions are recorded.
- Required project knowledge is not marked stale.

### Detailed work
1. Define explicit input/output contracts.
2. Define domain entities or services introduced by the phase.
3. Add schemas/validators before mutation paths.
4. Implement the smallest vertical slice.
5. Add deterministic tests for success and failure behavior.
6. Add migration/rollback behavior where persistence or generated files are involved.
7. Add observability for state transitions and failures.
8. Integrate with existing Agentic Discipline behavior instead of duplicating it.
9. Add a phase-specific doctor/readiness check.
10. Dogfood the capability on the Agentic Discipline repository where safe.

### Required tests
- unit tests;
- invalid input tests;
- state transition tests;
- idempotency tests where applicable;
- rollback tests where applicable;
- concurrency tests where applicable;
- recovery tests where applicable;
- compatibility tests against current Agentic Discipline flows.

### Acceptance criteria
- Capability is callable through a stable application service or CLI contract.
- Failure states are explicit and machine-readable.
- No existing protected behavior is silently weakened.
- Required knowledge/evidence is persisted with provenance.
- Re-running the operation is safe or explicitly rejected.
- A user can understand the result without reading internal DB tables.

### Evidence required
- passing automated tests;
- representative CLI/API output;
- persisted artifact or DB assertion;
- rollback/recovery demonstration when applicable.

### Definition of Done
The phase is not complete because code exists. It is complete when the capability is verified, integrated, documented, and its failure modes are tested.


## P01 — Domain Kernel

### Objective
Define stable entities, IDs, lifecycle, provenance, confidence, authority, versions, and typed edges.

### Preconditions
- Prior dependency phases are verified.
- Current branch/workspace is clean or unrelated work is preserved.
- Relevant architectural decisions are recorded.
- Required project knowledge is not marked stale.

### Detailed work
1. Define explicit input/output contracts.
2. Define domain entities or services introduced by the phase.
3. Add schemas/validators before mutation paths.
4. Implement the smallest vertical slice.
5. Add deterministic tests for success and failure behavior.
6. Add migration/rollback behavior where persistence or generated files are involved.
7. Add observability for state transitions and failures.
8. Integrate with existing Agentic Discipline behavior instead of duplicating it.
9. Add a phase-specific doctor/readiness check.
10. Dogfood the capability on the Agentic Discipline repository where safe.

### Required tests
- unit tests;
- invalid input tests;
- state transition tests;
- idempotency tests where applicable;
- rollback tests where applicable;
- concurrency tests where applicable;
- recovery tests where applicable;
- compatibility tests against current Agentic Discipline flows.

### Acceptance criteria
- Capability is callable through a stable application service or CLI contract.
- Failure states are explicit and machine-readable.
- No existing protected behavior is silently weakened.
- Required knowledge/evidence is persisted with provenance.
- Re-running the operation is safe or explicitly rejected.
- A user can understand the result without reading internal DB tables.

### Evidence required
- passing automated tests;
- representative CLI/API output;
- persisted artifact or DB assertion;
- rollback/recovery demonstration when applicable.

### Definition of Done
The phase is not complete because code exists. It is complete when the capability is verified, integrated, documented, and its failure modes are tested.


## P02 — Persistence Layer

### Objective
Implement local transactional persistence with migrations and optimistic concurrency.

### Preconditions
- Prior dependency phases are verified.
- Current branch/workspace is clean or unrelated work is preserved.
- Relevant architectural decisions are recorded.
- Required project knowledge is not marked stale.

### Detailed work
1. Define explicit input/output contracts.
2. Define domain entities or services introduced by the phase.
3. Add schemas/validators before mutation paths.
4. Implement the smallest vertical slice.
5. Add deterministic tests for success and failure behavior.
6. Add migration/rollback behavior where persistence or generated files are involved.
7. Add observability for state transitions and failures.
8. Integrate with existing Agentic Discipline behavior instead of duplicating it.
9. Add a phase-specific doctor/readiness check.
10. Dogfood the capability on the Agentic Discipline repository where safe.

### Required tests
- unit tests;
- invalid input tests;
- state transition tests;
- idempotency tests where applicable;
- rollback tests where applicable;
- concurrency tests where applicable;
- recovery tests where applicable;
- compatibility tests against current Agentic Discipline flows.

### Acceptance criteria
- Capability is callable through a stable application service or CLI contract.
- Failure states are explicit and machine-readable.
- No existing protected behavior is silently weakened.
- Required knowledge/evidence is persisted with provenance.
- Re-running the operation is safe or explicitly rejected.
- A user can understand the result without reading internal DB tables.

### Evidence required
- passing automated tests;
- representative CLI/API output;
- persisted artifact or DB assertion;
- rollback/recovery demonstration when applicable.

### Definition of Done
The phase is not complete because code exists. It is complete when the capability is verified, integrated, documented, and its failure modes are tested.


## P03 — Knowledge Query Layer

### Objective
Provide current/historical graph traversal and traceability queries.

### Preconditions
- Prior dependency phases are verified.
- Current branch/workspace is clean or unrelated work is preserved.
- Relevant architectural decisions are recorded.
- Required project knowledge is not marked stale.

### Detailed work
1. Define explicit input/output contracts.
2. Define domain entities or services introduced by the phase.
3. Add schemas/validators before mutation paths.
4. Implement the smallest vertical slice.
5. Add deterministic tests for success and failure behavior.
6. Add migration/rollback behavior where persistence or generated files are involved.
7. Add observability for state transitions and failures.
8. Integrate with existing Agentic Discipline behavior instead of duplicating it.
9. Add a phase-specific doctor/readiness check.
10. Dogfood the capability on the Agentic Discipline repository where safe.

### Required tests
- unit tests;
- invalid input tests;
- state transition tests;
- idempotency tests where applicable;
- rollback tests where applicable;
- concurrency tests where applicable;
- recovery tests where applicable;
- compatibility tests against current Agentic Discipline flows.

### Acceptance criteria
- Capability is callable through a stable application service or CLI contract.
- Failure states are explicit and machine-readable.
- No existing protected behavior is silently weakened.
- Required knowledge/evidence is persisted with provenance.
- Re-running the operation is safe or explicitly rejected.
- A user can understand the result without reading internal DB tables.

### Evidence required
- passing automated tests;
- representative CLI/API output;
- persisted artifact or DB assertion;
- rollback/recovery demonstration when applicable.

### Definition of Done
The phase is not complete because code exists. It is complete when the capability is verified, integrated, documented, and its failure modes are tested.


## P04 — Discovery Coverage Engine

### Objective
Measure repository understanding and prevent false claims of full inspection.

### Preconditions
- Prior dependency phases are verified.
- Current branch/workspace is clean or unrelated work is preserved.
- Relevant architectural decisions are recorded.
- Required project knowledge is not marked stale.

### Detailed work
1. Define explicit input/output contracts.
2. Define domain entities or services introduced by the phase.
3. Add schemas/validators before mutation paths.
4. Implement the smallest vertical slice.
5. Add deterministic tests for success and failure behavior.
6. Add migration/rollback behavior where persistence or generated files are involved.
7. Add observability for state transitions and failures.
8. Integrate with existing Agentic Discipline behavior instead of duplicating it.
9. Add a phase-specific doctor/readiness check.
10. Dogfood the capability on the Agentic Discipline repository where safe.

### Required tests
- unit tests;
- invalid input tests;
- state transition tests;
- idempotency tests where applicable;
- rollback tests where applicable;
- concurrency tests where applicable;
- recovery tests where applicable;
- compatibility tests against current Agentic Discipline flows.

### Acceptance criteria
- Capability is callable through a stable application service or CLI contract.
- Failure states are explicit and machine-readable.
- No existing protected behavior is silently weakened.
- Required knowledge/evidence is persisted with provenance.
- Re-running the operation is safe or explicitly rejected.
- A user can understand the result without reading internal DB tables.

### Evidence required
- passing automated tests;
- representative CLI/API output;
- persisted artifact or DB assertion;
- rollback/recovery demonstration when applicable.

### Definition of Done
The phase is not complete because code exists. It is complete when the capability is verified, integrated, documented, and its failure modes are tested.


## P05 — Project Adoption Engine

### Objective
Safely bootstrap Agentic Discipline 2.0 into an existing project.

### Preconditions
- Prior dependency phases are verified.
- Current branch/workspace is clean or unrelated work is preserved.
- Relevant architectural decisions are recorded.
- Required project knowledge is not marked stale.

### Detailed work
1. Define explicit input/output contracts.
2. Define domain entities or services introduced by the phase.
3. Add schemas/validators before mutation paths.
4. Implement the smallest vertical slice.
5. Add deterministic tests for success and failure behavior.
6. Add migration/rollback behavior where persistence or generated files are involved.
7. Add observability for state transitions and failures.
8. Integrate with existing Agentic Discipline behavior instead of duplicating it.
9. Add a phase-specific doctor/readiness check.
10. Dogfood the capability on the Agentic Discipline repository where safe.

### Required tests
- unit tests;
- invalid input tests;
- state transition tests;
- idempotency tests where applicable;
- rollback tests where applicable;
- concurrency tests where applicable;
- recovery tests where applicable;
- compatibility tests against current Agentic Discipline flows.

### Acceptance criteria
- Capability is callable through a stable application service or CLI contract.
- Failure states are explicit and machine-readable.
- No existing protected behavior is silently weakened.
- Required knowledge/evidence is persisted with provenance.
- Re-running the operation is safe or explicitly rejected.
- A user can understand the result without reading internal DB tables.

### Evidence required
- passing automated tests;
- representative CLI/API output;
- persisted artifact or DB assertion;
- rollback/recovery demonstration when applicable.

### Definition of Done
The phase is not complete because code exists. It is complete when the capability is verified, integrated, documented, and its failure modes are tested.


## P06 — Claim Reconciliation

### Objective
Convert raw evidence into claims and canonical knowledge without silent conflict loss.

### Preconditions
- Prior dependency phases are verified.
- Current branch/workspace is clean or unrelated work is preserved.
- Relevant architectural decisions are recorded.
- Required project knowledge is not marked stale.

### Detailed work
1. Define explicit input/output contracts.
2. Define domain entities or services introduced by the phase.
3. Add schemas/validators before mutation paths.
4. Implement the smallest vertical slice.
5. Add deterministic tests for success and failure behavior.
6. Add migration/rollback behavior where persistence or generated files are involved.
7. Add observability for state transitions and failures.
8. Integrate with existing Agentic Discipline behavior instead of duplicating it.
9. Add a phase-specific doctor/readiness check.
10. Dogfood the capability on the Agentic Discipline repository where safe.

### Required tests
- unit tests;
- invalid input tests;
- state transition tests;
- idempotency tests where applicable;
- rollback tests where applicable;
- concurrency tests where applicable;
- recovery tests where applicable;
- compatibility tests against current Agentic Discipline flows.

### Acceptance criteria
- Capability is callable through a stable application service or CLI contract.
- Failure states are explicit and machine-readable.
- No existing protected behavior is silently weakened.
- Required knowledge/evidence is persisted with provenance.
- Re-running the operation is safe or explicitly rejected.
- A user can understand the result without reading internal DB tables.

### Evidence required
- passing automated tests;
- representative CLI/API output;
- persisted artifact or DB assertion;
- rollback/recovery demonstration when applicable.

### Definition of Done
The phase is not complete because code exists. It is complete when the capability is verified, integrated, documented, and its failure modes are tested.


## P07 — Plan Intelligence

### Objective
Audit plans and project state for completeness, consistency, testability, and autonomy readiness.

### Preconditions
- Prior dependency phases are verified.
- Current branch/workspace is clean or unrelated work is preserved.
- Relevant architectural decisions are recorded.
- Required project knowledge is not marked stale.

### Detailed work
1. Define explicit input/output contracts.
2. Define domain entities or services introduced by the phase.
3. Add schemas/validators before mutation paths.
4. Implement the smallest vertical slice.
5. Add deterministic tests for success and failure behavior.
6. Add migration/rollback behavior where persistence or generated files are involved.
7. Add observability for state transitions and failures.
8. Integrate with existing Agentic Discipline behavior instead of duplicating it.
9. Add a phase-specific doctor/readiness check.
10. Dogfood the capability on the Agentic Discipline repository where safe.

### Required tests
- unit tests;
- invalid input tests;
- state transition tests;
- idempotency tests where applicable;
- rollback tests where applicable;
- concurrency tests where applicable;
- recovery tests where applicable;
- compatibility tests against current Agentic Discipline flows.

### Acceptance criteria
- Capability is callable through a stable application service or CLI contract.
- Failure states are explicit and machine-readable.
- No existing protected behavior is silently weakened.
- Required knowledge/evidence is persisted with provenance.
- Re-running the operation is safe or explicitly rejected.
- A user can understand the result without reading internal DB tables.

### Evidence required
- passing automated tests;
- representative CLI/API output;
- persisted artifact or DB assertion;
- rollback/recovery demonstration when applicable.

### Definition of Done
The phase is not complete because code exists. It is complete when the capability is verified, integrated, documented, and its failure modes are tested.


## P08 — Readiness Gate

### Objective
Return READY, READY_WITH_MANAGED_UNCERTAINTY, or BLOCKED with reasons.

### Preconditions
- Prior dependency phases are verified.
- Current branch/workspace is clean or unrelated work is preserved.
- Relevant architectural decisions are recorded.
- Required project knowledge is not marked stale.

### Detailed work
1. Define explicit input/output contracts.
2. Define domain entities or services introduced by the phase.
3. Add schemas/validators before mutation paths.
4. Implement the smallest vertical slice.
5. Add deterministic tests for success and failure behavior.
6. Add migration/rollback behavior where persistence or generated files are involved.
7. Add observability for state transitions and failures.
8. Integrate with existing Agentic Discipline behavior instead of duplicating it.
9. Add a phase-specific doctor/readiness check.
10. Dogfood the capability on the Agentic Discipline repository where safe.

### Required tests
- unit tests;
- invalid input tests;
- state transition tests;
- idempotency tests where applicable;
- rollback tests where applicable;
- concurrency tests where applicable;
- recovery tests where applicable;
- compatibility tests against current Agentic Discipline flows.

### Acceptance criteria
- Capability is callable through a stable application service or CLI contract.
- Failure states are explicit and machine-readable.
- No existing protected behavior is silently weakened.
- Required knowledge/evidence is persisted with provenance.
- Re-running the operation is safe or explicitly rejected.
- A user can understand the result without reading internal DB tables.

### Evidence required
- passing automated tests;
- representative CLI/API output;
- persisted artifact or DB assertion;
- rollback/recovery demonstration when applicable.

### Definition of Done
The phase is not complete because code exists. It is complete when the capability is verified, integrated, documented, and its failure modes are tested.


## P09 — Task Contracts

### Objective
Turn approved work into transferable, independently verifiable task contracts.

### Preconditions
- Prior dependency phases are verified.
- Current branch/workspace is clean or unrelated work is preserved.
- Relevant architectural decisions are recorded.
- Required project knowledge is not marked stale.

### Detailed work
1. Define explicit input/output contracts.
2. Define domain entities or services introduced by the phase.
3. Add schemas/validators before mutation paths.
4. Implement the smallest vertical slice.
5. Add deterministic tests for success and failure behavior.
6. Add migration/rollback behavior where persistence or generated files are involved.
7. Add observability for state transitions and failures.
8. Integrate with existing Agentic Discipline behavior instead of duplicating it.
9. Add a phase-specific doctor/readiness check.
10. Dogfood the capability on the Agentic Discipline repository where safe.

### Required tests
- unit tests;
- invalid input tests;
- state transition tests;
- idempotency tests where applicable;
- rollback tests where applicable;
- concurrency tests where applicable;
- recovery tests where applicable;
- compatibility tests against current Agentic Discipline flows.

### Acceptance criteria
- Capability is callable through a stable application service or CLI contract.
- Failure states are explicit and machine-readable.
- No existing protected behavior is silently weakened.
- Required knowledge/evidence is persisted with provenance.
- Re-running the operation is safe or explicitly rejected.
- A user can understand the result without reading internal DB tables.

### Evidence required
- passing automated tests;
- representative CLI/API output;
- persisted artifact or DB assertion;
- rollback/recovery demonstration when applicable.

### Definition of Done
The phase is not complete because code exists. It is complete when the capability is verified, integrated, documented, and its failure modes are tested.


## P10 — Execution Graph

### Objective
Model dependencies, blockers, states, and revalidation.

### Preconditions
- Prior dependency phases are verified.
- Current branch/workspace is clean or unrelated work is preserved.
- Relevant architectural decisions are recorded.
- Required project knowledge is not marked stale.

### Detailed work
1. Define explicit input/output contracts.
2. Define domain entities or services introduced by the phase.
3. Add schemas/validators before mutation paths.
4. Implement the smallest vertical slice.
5. Add deterministic tests for success and failure behavior.
6. Add migration/rollback behavior where persistence or generated files are involved.
7. Add observability for state transitions and failures.
8. Integrate with existing Agentic Discipline behavior instead of duplicating it.
9. Add a phase-specific doctor/readiness check.
10. Dogfood the capability on the Agentic Discipline repository where safe.

### Required tests
- unit tests;
- invalid input tests;
- state transition tests;
- idempotency tests where applicable;
- rollback tests where applicable;
- concurrency tests where applicable;
- recovery tests where applicable;
- compatibility tests against current Agentic Discipline flows.

### Acceptance criteria
- Capability is callable through a stable application service or CLI contract.
- Failure states are explicit and machine-readable.
- No existing protected behavior is silently weakened.
- Required knowledge/evidence is persisted with provenance.
- Re-running the operation is safe or explicitly rejected.
- A user can understand the result without reading internal DB tables.

### Evidence required
- passing automated tests;
- representative CLI/API output;
- persisted artifact or DB assertion;
- rollback/recovery demonstration when applicable.

### Definition of Done
The phase is not complete because code exists. It is complete when the capability is verified, integrated, documented, and its failure modes are tested.


## P11 — Context Engine

### Objective
Assemble minimum sufficient context with explicit budgets.

### Preconditions
- Prior dependency phases are verified.
- Current branch/workspace is clean or unrelated work is preserved.
- Relevant architectural decisions are recorded.
- Required project knowledge is not marked stale.

### Detailed work
1. Define explicit input/output contracts.
2. Define domain entities or services introduced by the phase.
3. Add schemas/validators before mutation paths.
4. Implement the smallest vertical slice.
5. Add deterministic tests for success and failure behavior.
6. Add migration/rollback behavior where persistence or generated files are involved.
7. Add observability for state transitions and failures.
8. Integrate with existing Agentic Discipline behavior instead of duplicating it.
9. Add a phase-specific doctor/readiness check.
10. Dogfood the capability on the Agentic Discipline repository where safe.

### Required tests
- unit tests;
- invalid input tests;
- state transition tests;
- idempotency tests where applicable;
- rollback tests where applicable;
- concurrency tests where applicable;
- recovery tests where applicable;
- compatibility tests against current Agentic Discipline flows.

### Acceptance criteria
- Capability is callable through a stable application service or CLI contract.
- Failure states are explicit and machine-readable.
- No existing protected behavior is silently weakened.
- Required knowledge/evidence is persisted with provenance.
- Re-running the operation is safe or explicitly rejected.
- A user can understand the result without reading internal DB tables.

### Evidence required
- passing automated tests;
- representative CLI/API output;
- persisted artifact or DB assertion;
- rollback/recovery demonstration when applicable.

### Definition of Done
The phase is not complete because code exists. It is complete when the capability is verified, integrated, documented, and its failure modes are tested.


## P12 — Continuity Engine

### Objective
Persist checkpoints and resume state independently from chat history.

### Preconditions
- Prior dependency phases are verified.
- Current branch/workspace is clean or unrelated work is preserved.
- Relevant architectural decisions are recorded.
- Required project knowledge is not marked stale.

### Detailed work
1. Define explicit input/output contracts.
2. Define domain entities or services introduced by the phase.
3. Add schemas/validators before mutation paths.
4. Implement the smallest vertical slice.
5. Add deterministic tests for success and failure behavior.
6. Add migration/rollback behavior where persistence or generated files are involved.
7. Add observability for state transitions and failures.
8. Integrate with existing Agentic Discipline behavior instead of duplicating it.
9. Add a phase-specific doctor/readiness check.
10. Dogfood the capability on the Agentic Discipline repository where safe.

### Required tests
- unit tests;
- invalid input tests;
- state transition tests;
- idempotency tests where applicable;
- rollback tests where applicable;
- concurrency tests where applicable;
- recovery tests where applicable;
- compatibility tests against current Agentic Discipline flows.

### Acceptance criteria
- Capability is callable through a stable application service or CLI contract.
- Failure states are explicit and machine-readable.
- No existing protected behavior is silently weakened.
- Required knowledge/evidence is persisted with provenance.
- Re-running the operation is safe or explicitly rejected.
- A user can understand the result without reading internal DB tables.

### Evidence required
- passing automated tests;
- representative CLI/API output;
- persisted artifact or DB assertion;
- rollback/recovery demonstration when applicable.

### Definition of Done
The phase is not complete because code exists. It is complete when the capability is verified, integrated, documented, and its failure modes are tested.


## P13 — Evidence Freshness

### Objective
Bind evidence to code and knowledge versions and invalidate stale proof.

### Preconditions
- Prior dependency phases are verified.
- Current branch/workspace is clean or unrelated work is preserved.
- Relevant architectural decisions are recorded.
- Required project knowledge is not marked stale.

### Detailed work
1. Define explicit input/output contracts.
2. Define domain entities or services introduced by the phase.
3. Add schemas/validators before mutation paths.
4. Implement the smallest vertical slice.
5. Add deterministic tests for success and failure behavior.
6. Add migration/rollback behavior where persistence or generated files are involved.
7. Add observability for state transitions and failures.
8. Integrate with existing Agentic Discipline behavior instead of duplicating it.
9. Add a phase-specific doctor/readiness check.
10. Dogfood the capability on the Agentic Discipline repository where safe.

### Required tests
- unit tests;
- invalid input tests;
- state transition tests;
- idempotency tests where applicable;
- rollback tests where applicable;
- concurrency tests where applicable;
- recovery tests where applicable;
- compatibility tests against current Agentic Discipline flows.

### Acceptance criteria
- Capability is callable through a stable application service or CLI contract.
- Failure states are explicit and machine-readable.
- No existing protected behavior is silently weakened.
- Required knowledge/evidence is persisted with provenance.
- Re-running the operation is safe or explicitly rejected.
- A user can understand the result without reading internal DB tables.

### Evidence required
- passing automated tests;
- representative CLI/API output;
- persisted artifact or DB assertion;
- rollback/recovery demonstration when applicable.

### Definition of Done
The phase is not complete because code exists. It is complete when the capability is verified, integrated, documented, and its failure modes are tested.


## P14 — Agent Registry

### Objective
Track workers, capabilities, sessions, and identity.

### Preconditions
- Prior dependency phases are verified.
- Current branch/workspace is clean or unrelated work is preserved.
- Relevant architectural decisions are recorded.
- Required project knowledge is not marked stale.

### Detailed work
1. Define explicit input/output contracts.
2. Define domain entities or services introduced by the phase.
3. Add schemas/validators before mutation paths.
4. Implement the smallest vertical slice.
5. Add deterministic tests for success and failure behavior.
6. Add migration/rollback behavior where persistence or generated files are involved.
7. Add observability for state transitions and failures.
8. Integrate with existing Agentic Discipline behavior instead of duplicating it.
9. Add a phase-specific doctor/readiness check.
10. Dogfood the capability on the Agentic Discipline repository where safe.

### Required tests
- unit tests;
- invalid input tests;
- state transition tests;
- idempotency tests where applicable;
- rollback tests where applicable;
- concurrency tests where applicable;
- recovery tests where applicable;
- compatibility tests against current Agentic Discipline flows.

### Acceptance criteria
- Capability is callable through a stable application service or CLI contract.
- Failure states are explicit and machine-readable.
- No existing protected behavior is silently weakened.
- Required knowledge/evidence is persisted with provenance.
- Re-running the operation is safe or explicitly rejected.
- A user can understand the result without reading internal DB tables.

### Evidence required
- passing automated tests;
- representative CLI/API output;
- persisted artifact or DB assertion;
- rollback/recovery demonstration when applicable.

### Definition of Done
The phase is not complete because code exists. It is complete when the capability is verified, integrated, documented, and its failure modes are tested.


## P15 — Leases

### Objective
Coordinate task ownership with expiry and recovery.

### Preconditions
- Prior dependency phases are verified.
- Current branch/workspace is clean or unrelated work is preserved.
- Relevant architectural decisions are recorded.
- Required project knowledge is not marked stale.

### Detailed work
1. Define explicit input/output contracts.
2. Define domain entities or services introduced by the phase.
3. Add schemas/validators before mutation paths.
4. Implement the smallest vertical slice.
5. Add deterministic tests for success and failure behavior.
6. Add migration/rollback behavior where persistence or generated files are involved.
7. Add observability for state transitions and failures.
8. Integrate with existing Agentic Discipline behavior instead of duplicating it.
9. Add a phase-specific doctor/readiness check.
10. Dogfood the capability on the Agentic Discipline repository where safe.

### Required tests
- unit tests;
- invalid input tests;
- state transition tests;
- idempotency tests where applicable;
- rollback tests where applicable;
- concurrency tests where applicable;
- recovery tests where applicable;
- compatibility tests against current Agentic Discipline flows.

### Acceptance criteria
- Capability is callable through a stable application service or CLI contract.
- Failure states are explicit and machine-readable.
- No existing protected behavior is silently weakened.
- Required knowledge/evidence is persisted with provenance.
- Re-running the operation is safe or explicitly rejected.
- A user can understand the result without reading internal DB tables.

### Evidence required
- passing automated tests;
- representative CLI/API output;
- persisted artifact or DB assertion;
- rollback/recovery demonstration when applicable.

### Definition of Done
The phase is not complete because code exists. It is complete when the capability is verified, integrated, documented, and its failure modes are tested.


## P16 — Workspace Isolation

### Objective
Provision worktrees/branches/sandboxes for parallel workers.

### Preconditions
- Prior dependency phases are verified.
- Current branch/workspace is clean or unrelated work is preserved.
- Relevant architectural decisions are recorded.
- Required project knowledge is not marked stale.

### Detailed work
1. Define explicit input/output contracts.
2. Define domain entities or services introduced by the phase.
3. Add schemas/validators before mutation paths.
4. Implement the smallest vertical slice.
5. Add deterministic tests for success and failure behavior.
6. Add migration/rollback behavior where persistence or generated files are involved.
7. Add observability for state transitions and failures.
8. Integrate with existing Agentic Discipline behavior instead of duplicating it.
9. Add a phase-specific doctor/readiness check.
10. Dogfood the capability on the Agentic Discipline repository where safe.

### Required tests
- unit tests;
- invalid input tests;
- state transition tests;
- idempotency tests where applicable;
- rollback tests where applicable;
- concurrency tests where applicable;
- recovery tests where applicable;
- compatibility tests against current Agentic Discipline flows.

### Acceptance criteria
- Capability is callable through a stable application service or CLI contract.
- Failure states are explicit and machine-readable.
- No existing protected behavior is silently weakened.
- Required knowledge/evidence is persisted with provenance.
- Re-running the operation is safe or explicitly rejected.
- A user can understand the result without reading internal DB tables.

### Evidence required
- passing automated tests;
- representative CLI/API output;
- persisted artifact or DB assertion;
- rollback/recovery demonstration when applicable.

### Definition of Done
The phase is not complete because code exists. It is complete when the capability is verified, integrated, documented, and its failure modes are tested.


## P17 — Parallel Safety

### Objective
Detect semantic overlap before concurrent execution.

### Preconditions
- Prior dependency phases are verified.
- Current branch/workspace is clean or unrelated work is preserved.
- Relevant architectural decisions are recorded.
- Required project knowledge is not marked stale.

### Detailed work
1. Define explicit input/output contracts.
2. Define domain entities or services introduced by the phase.
3. Add schemas/validators before mutation paths.
4. Implement the smallest vertical slice.
5. Add deterministic tests for success and failure behavior.
6. Add migration/rollback behavior where persistence or generated files are involved.
7. Add observability for state transitions and failures.
8. Integrate with existing Agentic Discipline behavior instead of duplicating it.
9. Add a phase-specific doctor/readiness check.
10. Dogfood the capability on the Agentic Discipline repository where safe.

### Required tests
- unit tests;
- invalid input tests;
- state transition tests;
- idempotency tests where applicable;
- rollback tests where applicable;
- concurrency tests where applicable;
- recovery tests where applicable;
- compatibility tests against current Agentic Discipline flows.

### Acceptance criteria
- Capability is callable through a stable application service or CLI contract.
- Failure states are explicit and machine-readable.
- No existing protected behavior is silently weakened.
- Required knowledge/evidence is persisted with provenance.
- Re-running the operation is safe or explicitly rejected.
- A user can understand the result without reading internal DB tables.

### Evidence required
- passing automated tests;
- representative CLI/API output;
- persisted artifact or DB assertion;
- rollback/recovery demonstration when applicable.

### Definition of Done
The phase is not complete because code exists. It is complete when the capability is verified, integrated, documented, and its failure modes are tested.


## P18 — Integration Gate

### Objective
Revalidate parallel work before merge into baseline.

### Preconditions
- Prior dependency phases are verified.
- Current branch/workspace is clean or unrelated work is preserved.
- Relevant architectural decisions are recorded.
- Required project knowledge is not marked stale.

### Detailed work
1. Define explicit input/output contracts.
2. Define domain entities or services introduced by the phase.
3. Add schemas/validators before mutation paths.
4. Implement the smallest vertical slice.
5. Add deterministic tests for success and failure behavior.
6. Add migration/rollback behavior where persistence or generated files are involved.
7. Add observability for state transitions and failures.
8. Integrate with existing Agentic Discipline behavior instead of duplicating it.
9. Add a phase-specific doctor/readiness check.
10. Dogfood the capability on the Agentic Discipline repository where safe.

### Required tests
- unit tests;
- invalid input tests;
- state transition tests;
- idempotency tests where applicable;
- rollback tests where applicable;
- concurrency tests where applicable;
- recovery tests where applicable;
- compatibility tests against current Agentic Discipline flows.

### Acceptance criteria
- Capability is callable through a stable application service or CLI contract.
- Failure states are explicit and machine-readable.
- No existing protected behavior is silently weakened.
- Required knowledge/evidence is persisted with provenance.
- Re-running the operation is safe or explicitly rejected.
- A user can understand the result without reading internal DB tables.

### Evidence required
- passing automated tests;
- representative CLI/API output;
- persisted artifact or DB assertion;
- rollback/recovery demonstration when applicable.

### Definition of Done
The phase is not complete because code exists. It is complete when the capability is verified, integrated, documented, and its failure modes are tested.


## P19 — Continuous Reconciliation

### Objective
Detect external/manual changes and update affected knowledge.

### Preconditions
- Prior dependency phases are verified.
- Current branch/workspace is clean or unrelated work is preserved.
- Relevant architectural decisions are recorded.
- Required project knowledge is not marked stale.

### Detailed work
1. Define explicit input/output contracts.
2. Define domain entities or services introduced by the phase.
3. Add schemas/validators before mutation paths.
4. Implement the smallest vertical slice.
5. Add deterministic tests for success and failure behavior.
6. Add migration/rollback behavior where persistence or generated files are involved.
7. Add observability for state transitions and failures.
8. Integrate with existing Agentic Discipline behavior instead of duplicating it.
9. Add a phase-specific doctor/readiness check.
10. Dogfood the capability on the Agentic Discipline repository where safe.

### Required tests
- unit tests;
- invalid input tests;
- state transition tests;
- idempotency tests where applicable;
- rollback tests where applicable;
- concurrency tests where applicable;
- recovery tests where applicable;
- compatibility tests against current Agentic Discipline flows.

### Acceptance criteria
- Capability is callable through a stable application service or CLI contract.
- Failure states are explicit and machine-readable.
- No existing protected behavior is silently weakened.
- Required knowledge/evidence is persisted with provenance.
- Re-running the operation is safe or explicitly rejected.
- A user can understand the result without reading internal DB tables.

### Evidence required
- passing automated tests;
- representative CLI/API output;
- persisted artifact or DB assertion;
- rollback/recovery demonstration when applicable.

### Definition of Done
The phase is not complete because code exists. It is complete when the capability is verified, integrated, documented, and its failure modes are tested.


## P20 — Evolution Hygiene

### Objective
Manage deprecations, temporary artifacts, replacements, and semantic garbage collection.

### Preconditions
- Prior dependency phases are verified.
- Current branch/workspace is clean or unrelated work is preserved.
- Relevant architectural decisions are recorded.
- Required project knowledge is not marked stale.

### Detailed work
1. Define explicit input/output contracts.
2. Define domain entities or services introduced by the phase.
3. Add schemas/validators before mutation paths.
4. Implement the smallest vertical slice.
5. Add deterministic tests for success and failure behavior.
6. Add migration/rollback behavior where persistence or generated files are involved.
7. Add observability for state transitions and failures.
8. Integrate with existing Agentic Discipline behavior instead of duplicating it.
9. Add a phase-specific doctor/readiness check.
10. Dogfood the capability on the Agentic Discipline repository where safe.

### Required tests
- unit tests;
- invalid input tests;
- state transition tests;
- idempotency tests where applicable;
- rollback tests where applicable;
- concurrency tests where applicable;
- recovery tests where applicable;
- compatibility tests against current Agentic Discipline flows.

### Acceptance criteria
- Capability is callable through a stable application service or CLI contract.
- Failure states are explicit and machine-readable.
- No existing protected behavior is silently weakened.
- Required knowledge/evidence is persisted with provenance.
- Re-running the operation is safe or explicitly rejected.
- A user can understand the result without reading internal DB tables.

### Evidence required
- passing automated tests;
- representative CLI/API output;
- persisted artifact or DB assertion;
- rollback/recovery demonstration when applicable.

### Definition of Done
The phase is not complete because code exists. It is complete when the capability is verified, integrated, documented, and its failure modes are tested.


## P21 — Governance and Budgets

### Objective
Apply permissions, protected actions, secret boundaries, and bounded autonomy.

### Preconditions
- Prior dependency phases are verified.
- Current branch/workspace is clean or unrelated work is preserved.
- Relevant architectural decisions are recorded.
- Required project knowledge is not marked stale.

### Detailed work
1. Define explicit input/output contracts.
2. Define domain entities or services introduced by the phase.
3. Add schemas/validators before mutation paths.
4. Implement the smallest vertical slice.
5. Add deterministic tests for success and failure behavior.
6. Add migration/rollback behavior where persistence or generated files are involved.
7. Add observability for state transitions and failures.
8. Integrate with existing Agentic Discipline behavior instead of duplicating it.
9. Add a phase-specific doctor/readiness check.
10. Dogfood the capability on the Agentic Discipline repository where safe.

### Required tests
- unit tests;
- invalid input tests;
- state transition tests;
- idempotency tests where applicable;
- rollback tests where applicable;
- concurrency tests where applicable;
- recovery tests where applicable;
- compatibility tests against current Agentic Discipline flows.

### Acceptance criteria
- Capability is callable through a stable application service or CLI contract.
- Failure states are explicit and machine-readable.
- No existing protected behavior is silently weakened.
- Required knowledge/evidence is persisted with provenance.
- Re-running the operation is safe or explicitly rejected.
- A user can understand the result without reading internal DB tables.

### Evidence required
- passing automated tests;
- representative CLI/API output;
- persisted artifact or DB assertion;
- rollback/recovery demonstration when applicable.

### Definition of Done
The phase is not complete because code exists. It is complete when the capability is verified, integrated, documented, and its failure modes are tested.


## P22 — Observability

### Objective
Provide reconstructable timelines for tasks, agents, evidence, and knowledge mutations.

### Preconditions
- Prior dependency phases are verified.
- Current branch/workspace is clean or unrelated work is preserved.
- Relevant architectural decisions are recorded.
- Required project knowledge is not marked stale.

### Detailed work
1. Define explicit input/output contracts.
2. Define domain entities or services introduced by the phase.
3. Add schemas/validators before mutation paths.
4. Implement the smallest vertical slice.
5. Add deterministic tests for success and failure behavior.
6. Add migration/rollback behavior where persistence or generated files are involved.
7. Add observability for state transitions and failures.
8. Integrate with existing Agentic Discipline behavior instead of duplicating it.
9. Add a phase-specific doctor/readiness check.
10. Dogfood the capability on the Agentic Discipline repository where safe.

### Required tests
- unit tests;
- invalid input tests;
- state transition tests;
- idempotency tests where applicable;
- rollback tests where applicable;
- concurrency tests where applicable;
- recovery tests where applicable;
- compatibility tests against current Agentic Discipline flows.

### Acceptance criteria
- Capability is callable through a stable application service or CLI contract.
- Failure states are explicit and machine-readable.
- No existing protected behavior is silently weakened.
- Required knowledge/evidence is persisted with provenance.
- Re-running the operation is safe or explicitly rejected.
- A user can understand the result without reading internal DB tables.

### Evidence required
- passing automated tests;
- representative CLI/API output;
- persisted artifact or DB assertion;
- rollback/recovery demonstration when applicable.

### Definition of Done
The phase is not complete because code exists. It is complete when the capability is verified, integrated, documented, and its failure modes are tested.


## P23 — MCP Interface

### Objective
Expose model-agnostic coordination operations.

### Preconditions
- Prior dependency phases are verified.
- Current branch/workspace is clean or unrelated work is preserved.
- Relevant architectural decisions are recorded.
- Required project knowledge is not marked stale.

### Detailed work
1. Define explicit input/output contracts.
2. Define domain entities or services introduced by the phase.
3. Add schemas/validators before mutation paths.
4. Implement the smallest vertical slice.
5. Add deterministic tests for success and failure behavior.
6. Add migration/rollback behavior where persistence or generated files are involved.
7. Add observability for state transitions and failures.
8. Integrate with existing Agentic Discipline behavior instead of duplicating it.
9. Add a phase-specific doctor/readiness check.
10. Dogfood the capability on the Agentic Discipline repository where safe.

### Required tests
- unit tests;
- invalid input tests;
- state transition tests;
- idempotency tests where applicable;
- rollback tests where applicable;
- concurrency tests where applicable;
- recovery tests where applicable;
- compatibility tests against current Agentic Discipline flows.

### Acceptance criteria
- Capability is callable through a stable application service or CLI contract.
- Failure states are explicit and machine-readable.
- No existing protected behavior is silently weakened.
- Required knowledge/evidence is persisted with provenance.
- Re-running the operation is safe or explicitly rejected.
- A user can understand the result without reading internal DB tables.

### Evidence required
- passing automated tests;
- representative CLI/API output;
- persisted artifact or DB assertion;
- rollback/recovery demonstration when applicable.

### Definition of Done
The phase is not complete because code exists. It is complete when the capability is verified, integrated, documented, and its failure modes are tested.


## P24 — Project Console

### Objective
Provide human-readable status and decision UX.

### Preconditions
- Prior dependency phases are verified.
- Current branch/workspace is clean or unrelated work is preserved.
- Relevant architectural decisions are recorded.
- Required project knowledge is not marked stale.

### Detailed work
1. Define explicit input/output contracts.
2. Define domain entities or services introduced by the phase.
3. Add schemas/validators before mutation paths.
4. Implement the smallest vertical slice.
5. Add deterministic tests for success and failure behavior.
6. Add migration/rollback behavior where persistence or generated files are involved.
7. Add observability for state transitions and failures.
8. Integrate with existing Agentic Discipline behavior instead of duplicating it.
9. Add a phase-specific doctor/readiness check.
10. Dogfood the capability on the Agentic Discipline repository where safe.

### Required tests
- unit tests;
- invalid input tests;
- state transition tests;
- idempotency tests where applicable;
- rollback tests where applicable;
- concurrency tests where applicable;
- recovery tests where applicable;
- compatibility tests against current Agentic Discipline flows.

### Acceptance criteria
- Capability is callable through a stable application service or CLI contract.
- Failure states are explicit and machine-readable.
- No existing protected behavior is silently weakened.
- Required knowledge/evidence is persisted with provenance.
- Re-running the operation is safe or explicitly rejected.
- A user can understand the result without reading internal DB tables.

### Evidence required
- passing automated tests;
- representative CLI/API output;
- persisted artifact or DB assertion;
- rollback/recovery demonstration when applicable.

### Definition of Done
The phase is not complete because code exists. It is complete when the capability is verified, integrated, documented, and its failure modes are tested.


## P25 — Self-Verification

### Objective
Stress the platform with synthetic projects and fault injection.

### Preconditions
- Prior dependency phases are verified.
- Current branch/workspace is clean or unrelated work is preserved.
- Relevant architectural decisions are recorded.
- Required project knowledge is not marked stale.

### Detailed work
1. Define explicit input/output contracts.
2. Define domain entities or services introduced by the phase.
3. Add schemas/validators before mutation paths.
4. Implement the smallest vertical slice.
5. Add deterministic tests for success and failure behavior.
6. Add migration/rollback behavior where persistence or generated files are involved.
7. Add observability for state transitions and failures.
8. Integrate with existing Agentic Discipline behavior instead of duplicating it.
9. Add a phase-specific doctor/readiness check.
10. Dogfood the capability on the Agentic Discipline repository where safe.

### Required tests
- unit tests;
- invalid input tests;
- state transition tests;
- idempotency tests where applicable;
- rollback tests where applicable;
- concurrency tests where applicable;
- recovery tests where applicable;
- compatibility tests against current Agentic Discipline flows.

### Acceptance criteria
- Capability is callable through a stable application service or CLI contract.
- Failure states are explicit and machine-readable.
- No existing protected behavior is silently weakened.
- Required knowledge/evidence is persisted with provenance.
- Re-running the operation is safe or explicitly rejected.
- A user can understand the result without reading internal DB tables.

### Evidence required
- passing automated tests;
- representative CLI/API output;
- persisted artifact or DB assertion;
- rollback/recovery demonstration when applicable.

### Definition of Done
The phase is not complete because code exists. It is complete when the capability is verified, integrated, documented, and its failure modes are tested.


## P26 — Dogfooding

### Objective
Use AD2 to manage AD2 itself.

### Preconditions
- Prior dependency phases are verified.
- Current branch/workspace is clean or unrelated work is preserved.
- Relevant architectural decisions are recorded.
- Required project knowledge is not marked stale.

### Detailed work
1. Define explicit input/output contracts.
2. Define domain entities or services introduced by the phase.
3. Add schemas/validators before mutation paths.
4. Implement the smallest vertical slice.
5. Add deterministic tests for success and failure behavior.
6. Add migration/rollback behavior where persistence or generated files are involved.
7. Add observability for state transitions and failures.
8. Integrate with existing Agentic Discipline behavior instead of duplicating it.
9. Add a phase-specific doctor/readiness check.
10. Dogfood the capability on the Agentic Discipline repository where safe.

### Required tests
- unit tests;
- invalid input tests;
- state transition tests;
- idempotency tests where applicable;
- rollback tests where applicable;
- concurrency tests where applicable;
- recovery tests where applicable;
- compatibility tests against current Agentic Discipline flows.

### Acceptance criteria
- Capability is callable through a stable application service or CLI contract.
- Failure states are explicit and machine-readable.
- No existing protected behavior is silently weakened.
- Required knowledge/evidence is persisted with provenance.
- Re-running the operation is safe or explicitly rejected.
- A user can understand the result without reading internal DB tables.

### Evidence required
- passing automated tests;
- representative CLI/API output;
- persisted artifact or DB assertion;
- rollback/recovery demonstration when applicable.

### Definition of Done
The phase is not complete because code exists. It is complete when the capability is verified, integrated, documented, and its failure modes are tested.


## P27 — Release Hardening

### Objective
Finalize migration, compatibility, docs, performance, and stable release evidence.

### Preconditions
- Prior dependency phases are verified.
- Current branch/workspace is clean or unrelated work is preserved.
- Relevant architectural decisions are recorded.
- Required project knowledge is not marked stale.

### Detailed work
1. Define explicit input/output contracts.
2. Define domain entities or services introduced by the phase.
3. Add schemas/validators before mutation paths.
4. Implement the smallest vertical slice.
5. Add deterministic tests for success and failure behavior.
6. Add migration/rollback behavior where persistence or generated files are involved.
7. Add observability for state transitions and failures.
8. Integrate with existing Agentic Discipline behavior instead of duplicating it.
9. Add a phase-specific doctor/readiness check.
10. Dogfood the capability on the Agentic Discipline repository where safe.

### Required tests
- unit tests;
- invalid input tests;
- state transition tests;
- idempotency tests where applicable;
- rollback tests where applicable;
- concurrency tests where applicable;
- recovery tests where applicable;
- compatibility tests against current Agentic Discipline flows.

### Acceptance criteria
- Capability is callable through a stable application service or CLI contract.
- Failure states are explicit and machine-readable.
- No existing protected behavior is silently weakened.
- Required knowledge/evidence is persisted with provenance.
- Re-running the operation is safe or explicitly rejected.
- A user can understand the result without reading internal DB tables.

### Evidence required
- passing automated tests;
- representative CLI/API output;
- persisted artifact or DB assertion;
- rollback/recovery demonstration when applicable.

### Definition of Done
The phase is not complete because code exists. It is complete when the capability is verified, integrated, documented, and its failure modes are tested.
