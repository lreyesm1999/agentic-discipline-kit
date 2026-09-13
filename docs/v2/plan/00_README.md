# Agentic Discipline 2.0 — Hyperdetailed Implementation Plan

## Purpose

This package is the implementation blueprint for evolving the existing **Agentic Discipline Kit** into **Agentic Discipline 2.0**: a local-first, model-agnostic engineering control plane for autonomous software delivery.

The target system must support:

- adoption of existing repositories without requiring a full human re-explanation;
- measurable project discovery and understanding;
- a knowledge platform composed of multiple specialized graphs rather than one universal graph;
- evidence-backed planning, execution, and completion;
- persistent task state across sessions and models;
- multi-agent coordination using leases and isolated workspaces;
- context-efficient retrieval and handoff;
- continuous reconciliation between repository reality and project knowledge;
- lifecycle and semantic cleanup so obsolete requirements do not return;
- explicit governance, autonomy budgets, provenance, and observability;
- deterministic integration and verification gates;
- human-readable project visibility through a console;
- safe study of external projects through an influence ledger without copying third-party code.

## Core operating loop

```text
DISCOVER
→ UNDERSTAND
→ STRUCTURE
→ AUDIT
→ PLAN
→ EXECUTE
→ TEST
→ VERIFY
→ CHECKPOINT
→ RECORD
→ RECONCILE
→ CONTINUE
```

## Three laws

1. **Autonomy:** keep moving while safe executable work exists.
2. **Evidence:** `COMPLETED` means verified, not narrated.
3. **Persistence:** the chat/session may disappear; project state must not.

## Major architectural correction

Do not build one ambiguous "knowledge graph".

Build a **Knowledge Platform** containing specialized graph domains:

```text
Knowledge Platform
├── Product / Requirement Graph
├── Architecture Graph
├── Code Graph
├── Decision Graph
├── Execution Graph
├── Evidence Graph
└── Evolution / History Graph
```

The graphs may reference each other but preserve separate semantics and authority.

## Recommended implementation posture

Start as a **modular monolith** with local persistence and explicit boundaries.

Do not introduce microservices, distributed databases, Kafka, Kubernetes, or a dedicated graph database unless later evidence proves they are needed.

A strong initial target is:

- TypeScript or Python control plane, selected after current-repo audit;
- SQLite for local-first persistence;
- relational tables with typed edges;
- JSON Schema / Pydantic / Zod style contract validation;
- CLI first;
- MCP second;
- API third;
- web console after the control plane is stable.

## Read order

Start with:

1. `01_PRODUCT_VISION_AND_NON_NEGOTIABLES.md`
2. `02_CURRENT_TO_TARGET_GAP_MODEL.md`
3. `03_TARGET_ARCHITECTURE.md`
4. `20_IMPLEMENTATION_ROADMAP.md`
5. `21_PHASE_BY_PHASE_PLAN.md`

Then use the subsystem documents as implementation contracts.

## Definition of success

Agentic Discipline 2.0 is successful when it can demonstrate all of the following:

- adopt an unfamiliar existing repository;
- construct a useful, provenance-aware knowledge baseline;
- continue work after the original model/session disappears;
- coordinate multiple independent subscriptions/tools without a central LLM account;
- prevent stale documentation from silently reintroducing removed behavior;
- parallelize safe work while isolating conflicting work;
- invalidate stale evidence after relevant code or requirement changes;
- produce a human-readable explanation of what is happening and why;
- refuse to mark work complete without configured proof.
