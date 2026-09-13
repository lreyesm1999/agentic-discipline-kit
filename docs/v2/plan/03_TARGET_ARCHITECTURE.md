# Target Architecture

## Logical architecture

```text
                             HUMAN
                               │
                       Project Console
                               │
                     ┌─────────┴─────────┐
                     │   Control Plane   │
                     └─────────┬─────────┘
                               │
                  ┌────────────┴────────────┐
                  │   Knowledge Platform    │
                  │                         │
                  │ Requirement Graph       │
                  │ Architecture Graph      │
                  │ Code Graph              │
                  │ Decision Graph          │
                  │ Execution Graph         │
                  │ Evidence Graph          │
                  │ Evolution Graph         │
                  └────────────┬────────────┘
                               │
          ┌────────────────────┼─────────────────────┐
          │                    │                     │
   Discovery Engine      Context Engine      Plan Intelligence
          │                    │                     │
          └────────────────────┼─────────────────────┘
                               │
                        Execution Engine
                               │
                         Orchestrator
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
       Cursor               Claude               Codex
       worker               worker               worker
          │                    │                    │
       worktree             worktree             worktree
          └────────────────────┼────────────────────┘
                               │
                       Integration Gate
                               │
                        Verification
                               │
                           Evidence
                               │
                       Reconciliation
                               │
                      Evolution / Hygiene
```

## Cross-cutting concerns

Every subsystem must respect:

- provenance;
- authority;
- versioning;
- optimistic concurrency;
- permissions;
- autonomy budgets;
- observability;
- context budgets;
- auditability.

## Recommended first implementation shape

### Modular monolith

Suggested modules:

```text
core/
  ids/
  contracts/
  errors/
  events/

knowledge/
  entities/
  edges/
  provenance/
  versioning/
  queries/
  invariants/

discovery/
  scanners/
  coverage/
  baseline/

planning/
  audit/
  gaps/
  readiness/

execution/
  tasks/
  state-machine/
  checkpoints/
  leases/
  workspaces/

context/
  builder/
  budgets/
  handoff/

verification/
  evidence/
  invalidation/
  integration/

reconciliation/
  change-detection/
  impact/
  lifecycle/

governance/
  permissions/
  budgets/
  policy/

interfaces/
  cli/
  mcp/
  api/

console/
  web/
```

## Initial persistence

Recommended default:
- SQLite;
- WAL mode;
- foreign keys on;
- application-level repository/unit-of-work;
- version columns for optimistic concurrency;
- append-only event/audit table;
- FTS for textual lookup;
- typed edge table for graph relationships.

Do not require a graph database in v2.0 MVP.

## Optional later evolution

When proven necessary:
- PostgreSQL for team/shared mode;
- background workers;
- remote orchestration;
- distributed leases;
- dedicated graph engine;
- centralized server mode.
