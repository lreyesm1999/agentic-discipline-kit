# Agentic Discipline 2.1 — Adaptive Assurance Engine: design and dependency order

## The change in one sentence

2.0 asks "did the task's verifiers pass?". 2.1 asks "is every claim this change
must keep true currently supported by evidence?" — and refuses completion while
any mandatory claim is not.

```text
Change / Task
  -> Assurance Compiler      obligations this change must keep true
  -> Proof Planner           cheapest sufficient evidence route per obligation
  -> Verifier selection      capabilities, not tool names
  -> Evidence                real executions, hashed artifacts
  -> Evidence Resolution     per-obligation freshness and conflict
  -> Assurance State         VERIFIED / FAILED / UNKNOWN / STALE / CONFLICTED / ...
  -> Decision                CONTINUE REPAIR EXPAND BLOCK ESCALATE HUMAN COMPLETE
```

## Reuse of 2.0 (nothing here is rebuilt)

| 2.1 need | 2.0 capability reused |
|---|---|
| Persistence, optimistic versions, hash-linked audit | `control/store.py` (`records` is kind-keyed; obligations are a new kind) |
| Evidence freshness binding | `control/verification.py` `binding` / `fresh` — narrowed per obligation |
| Verifier execution, redaction, artifacts | `verify()` and `quality.run_gate` — one execution path, now able to run a subset |
| Change scope, budgets, protected paths | `check_changes`, `policy()["protected_paths"]` |
| Deterministic risk signals | `risk.PATTERNS` — the policy source for compiled obligations |
| Dependency/impact traversal | `knowledge.impact`, code entities and edges |
| CLI / API / MCP / console | extended, one application layer |

## Dependency order (executed in this order)

```text
P01 model            obligation shape, statuses, capability vocabulary, deterministic ids
P02 persistence      schema 2 + explicit, idempotent, reversible migration
P03 compiler         obligations from contract, policy, risk and actual change
P04 registry         verifier capabilities, evidence classes, cost, levels
P05 planner          capability -> verifier, deterministic dominance, escalation
P06 runner           focused execution over the existing verify() path
P07 resolver         per-obligation freshness, conflicts, proof debt
P08 invalidation     staleness through the obligation binding
P09 impact           changed paths -> affected obligations -> expansion
P10 decision         assurance-governed autonomy
P11 interfaces       CLI, API, MCP over one service
P12 reference/adversarial/human verifier classes
P13 console          read-first assurance view
P14 migration        2.0 -> 2.1, legacy provenance
P15 hardening        property, failure injection, mutation, dogfood
```

Deviation from the suggested order: the verifier registry (P04) lands after the
compiler because the compiler needs only the capability vocabulary (P01), and the
registry's default descriptors are easier to justify once the compiler shows which
capabilities obligations actually ask for.

## Invariants the implementation must hold

1. A mandatory obligation never disappears without an audited waiver.
2. Assurance scope expands automatically; it contracts only through a waiver.
3. `STALE` evidence never satisfies an obligation.
4. `AGENT_JUDGMENT` never satisfies an obligation a deterministic verifier can reach.
5. One fresh `FAIL` next to a fresh `PASS` is `CONFLICTED`, never `PASS`.
6. `UNKNOWN` is never `PASS`.
7. No CLI, API or MCP path completes a task holding mandatory proof debt.
8. Current assurance state is recomputed from persisted facts, never trusted from a cache.
