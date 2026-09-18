# Implementation Roadmap

## Stage 0 — Audit and freeze assumptions
Deliver:
- current capability map;
- repository audit;
- reused-vs-new matrix;
- architecture decision record for runtime language/persistence.

Exit:
- no major subsystem begins before current state is mapped.

## Stage 1 — Domain kernel
Deliver:
- stable IDs;
- entities;
- typed relationships;
- provenance;
- confidence;
- authority;
- lifecycle;
- versioning primitives.

Exit:
- unit-tested domain model.

## Stage 2 — Local persistence
Deliver:
- SQLite schema;
- migrations;
- repository abstraction;
- optimistic concurrency;
- audit/event table.

Exit:
- transactional CRUD and conflict tests.

## Stage 3 — Knowledge query layer
Deliver:
- graph-style traversal;
- typed filters;
- historical/current queries;
- FTS.

Exit:
- can answer core traceability queries.

## Stage 4 — Discovery coverage
Deliver:
- repository scanner;
- coverage ledger;
- stack/profile detection;
- graph-first discovery contract.

Exit:
- measurable discovery report.

## Stage 5 — Adoption engine
Deliver:
- `agentic adopt`;
- dry-run;
- baseline;
- conflict detection;
- transactional install/bootstrap.

Exit:
- safely adopt an existing repo.

## Stage 6 — Canonicalization
Deliver:
- Evidence → Claims → Canonical;
- authority/confidence logic;
- contradiction storage.

Exit:
- conflicting documentation/code cases handled.

## Stage 7 — Plan Intelligence
Deliver:
- plan audit;
- gap classifier;
- Ask Last;
- readiness gate.

Exit:
- produces ready/managed-uncertainty/blocked.

## Stage 8 — Task contracts + Execution Graph
Deliver:
- task schema;
- state machine;
- dependencies;
- vertical slice planner.

Exit:
- executable graph generated from approved plan.

## Stage 9 — Context Engine
Deliver:
- minimum sufficient context;
- context audit;
- budgets;
- source references.

Exit:
- task context generated within budget.

## Stage 10 — Continuity
Deliver:
- checkpoints;
- context-low handling;
- resume package.

Exit:
- second agent resumes without chat history.

## Stage 11 — Evidence integration
Deliver:
- evidence records;
- freshness;
- invalidation;
- completion invariant.

Exit:
- cannot complete without current evidence.

## Stage 12 — Multi-agent coordination
Deliver:
- agents;
- capabilities;
- leases;
- heartbeat;
- task claiming.

Exit:
- multiple independent workers coordinate.

## Stage 13 — Workspace isolation
Deliver:
- worktree manager;
- branch policy;
- workspace cleanup.

Exit:
- parallel workers isolated.

## Stage 14 — Parallel safety + integration gate
Deliver:
- overlap detection;
- semantic risk;
- merge gate;
- cross-task verification.

Exit:
- safe parallel merge workflow.

## Stage 15 — Reconciliation
Deliver:
- Git change detection;
- impact analysis;
- external modification detection;
- graph refresh.

Exit:
- manual code changes reflected in knowledge.

## Stage 16 — Evolution hygiene
Deliver:
- lifecycle records;
- semantic GC;
- no-silent-resurrection checks.

Exit:
- retired feature cannot reappear from legacy docs.

## Stage 17 — Governance
Deliver:
- permission scopes;
- protected actions;
- autonomy budgets;
- secret handling.

Exit:
- agents constrained by policy.

## Stage 18 — Observability
Deliver:
- structured activity log;
- traces;
- task timeline;
- agent timeline.

Exit:
- can explain what happened and why.

## Stage 19 — MCP
Deliver:
- model-agnostic MCP surface;
- stable DTOs;
- permission checks.

Exit:
- Cursor/Claude/Codex-like workers can join shared plane.

## Stage 20 — Project Console
Deliver:
- read-first web UI;
- status;
- tasks;
- agents;
- evidence;
- decisions;
- stale knowledge.

Exit:
- human no longer needs DB/CLI inspection.

## Stage 21 — Self-verification
Deliver:
- synthetic repositories;
- failure injection;
- crash/recovery tests;
- lease expiry tests;
- stale evidence tests.

Exit:
- resilience demonstrated.

## Stage 22 — Dogfood migration
Deliver:
- run remaining AD2 work through AD2 itself.

Exit:
- real-world validation.

## Stage 23 — Stable v2 release
Deliver:
- migration guide;
- compatibility matrix;
- release evidence;
- performance baseline;
- known limitations.
