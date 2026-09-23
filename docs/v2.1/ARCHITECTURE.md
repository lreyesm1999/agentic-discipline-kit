# Assurance engine architecture

Everything here lives in `src/agentic_discipline/control/assurance/` and is reached
through the same application layer the CLI, API, MCP and console already share. Nothing in
2.0 was rewritten; the engine is a layer over the kernel that was already there.

## Components

| Module | Responsibility |
|---|---|
| `model.py` | obligation shape, statuses, the capability vocabulary, deterministic identity, and the monotonic merge that makes a plan unable to shrink |
| `registry.py` | what each verifier kind proves: capabilities, evidence class, cost, level, incrementality, inputs, artefacts |
| `compiler.py` | obligations from the task contract, repository policy, observed paths and what they reach |
| `impact.py` | the real diff, the symbols in it, and the requirements and files it reaches through recorded links |
| `planner.py` | capability to verifier, cheapest sufficient, falsification first, deterministic dominance, escalation depth |
| `resolver.py` | per-obligation binding, freshness, conflict, dominance, and proof debt |
| `decision.py` | what the work is allowed to do next |
| `service.py` | the one application layer: compile, reconcile, verify, status, explain, debt, waive, resolve, register, integrity |
| `migration.py` | the explicit, idempotent, reversible 2.0 to 2.1 upgrade |

The 2.0 modules gained four narrow changes and nothing else:

- `store.py` — schema 2 alongside schema 1, and `Store.schema_version`.
- `verification.py` — `verify()` can run a subset of the contract's verifiers, stamps each
  evidence record with the obligations it was run for and their bindings, records the
  evidence class and the judgment verdict for agent-judgment kinds, and `complete()`
  reconciles the plan and refuses a task holding mandatory proof debt.
- `api.py`, `cli.py`, `console.py` — the new operations, the `assurance` command group, and
  a read-only assurance view.

## Data model

Obligations, plans, waivers, capability declarations and migrations are new record kinds
in the existing `records` table, so they inherit optimistic versions, full revision history
and the hash-linked audit chain without a table migration.

```yaml
obligation:                      # kind "obligation"
  id: PO-<sha256(task_id, origin_key)[:16]>   # deterministic: a recompile updates, never duplicates
  task_id: TASK-...
  claim: "Financial results for existing data are unchanged by this change."
  origin:
    requirement_ids: [...]       # knowledge entities behind it
    acceptance_ids: [0]          # criterion indexes in the task contract
    policy_ids: [FIN-STABLE]     # the repository rule that raised it
    architecture_ids: [...]      # declared boundaries
    generated_reason: "observed money surface in src/billing/invoice.py"
  derivation: CONTRACT | POLICY | IMPACT
  criticality: LOW | STANDARD | HIGH | CRITICAL
  mandatory: true
  enforced: true                 # false while it is only a phase-A forecast
  phase: INITIAL | RECONCILED
  status: UNRESOLVED | WAIVED    # the only two an owner action sets; see below
  acceptable_proof_capabilities: [historical_stability, regression, property]
  required_verifiers: [<verifier digest>, ...]   # the current route
  level: 2                       # the depth this route sits at
  floor: 2                       # the shallowest route still allowed; only ever rises
  affected_paths: [src/billing/invoice.py]
  affected_symbols: ["src/billing/invoice.py::total"]
  plan: {route, covered, human_required, deterministic_available, unsatisfiable}
  waiver_id: WAIV-... | null
  created_at / updated_at

assurance_plan:                  # one record per compilation, so the plan has a history
  task_id, phase, obligations, added, widened, retained,
  refused_contractions, observed_paths, signals, impact, plan_digest, created_at

waiver:                          # the only sanctioned contraction
  obligation_id, task_id, claim, criticality, reason, authorization,
  status_when_waived, created_at

verifier_capability:             # an owner-registered project verifier kind
  id, capabilities, evidence_class, cost, level, supports_incremental,
  ecosystems, required_inputs, produced_artifacts, deterministic

assurance_migration:
  from_schema, to_schema, status, tasks, obligations,
  reclassified_evidence, reactivated, rollback_reason
```

Evidence records gained five fields, all written by the run that produced them:

```yaml
obligation_ids: [PO-..., ...]        # what this run was executed for
obligation_bindings: {PO-...: {...}} # what each of those claims depended on, before the run
evidence_class: DETERMINISTIC | MEASURED | AGENT_JUDGMENT | HUMAN
judgment: NO_COUNTEREXAMPLE_FOUND | COUNTEREXAMPLE_FOUND | INCONCLUSIVE   # judgment kinds only
run_consistent: true                 # whether the run's own inputs stayed still under it
assurance_provenance: LEGACY         # migration only
```

### Why `status` holds so little

`status` is the record state an **owner action** sets, and it is only ever `UNRESOLVED` or
`WAIVED`. The live assurance state — `VERIFIED`, `FAILED`, `STALE`, `CONFLICTED`,
`UNKNOWN`, `BLOCKED`, `HUMAN_REQUIRED` — is recomputed from persisted facts on every read
and is never cached. No stored verdict can outlive the facts behind it, and the integrity
check reports any obligation whose persisted status is not an owner state.

## How a claim is resolved

```text
evidence for this task
  -> related      : stamped with this obligation, or recorded against its acceptance criterion
  -> matched      : produced by a verifier this claim requires now (others are superseded)
  -> current      : run was self-consistent, artefact hash intact, artefact verdict agrees
                    with the row, and the obligation binding still matches
  -> proven       : current PASS, excluding AGENT_JUDGMENT while a deterministic route exists

FAIL and PASS among current  -> CONFLICTED
FAIL                         -> FAILED
BLOCKED                      -> BLOCKED
UNKNOWN                      -> UNKNOWN
no verifier required at all  -> UNKNOWN (with the planner's reason)
every required verifier proven -> VERIFIED
some evidence exists but none current -> STALE
otherwise                    -> UNRESOLVED
human route with nothing proven -> HUMAN_REQUIRED
```

## The obligation binding

```python
{
  "files":           fingerprint(workspace, obligation.affected_paths or task.scope),
  "protected_files": fingerprint(workspace, policy.protected_paths),
  "requirements":    {entity_id: version, ...},
  "acceptance":      digest([criterion texts this claim covers]),
  "verifiers":       digest(sorted(required_verifiers)),
  "claim":           digest(claim text),
  "policy":          digest(policy),
}
```

This is the 2.0 `binding()` narrowed to one claim. The 2.0 task-wide binding is still
computed for `completion_proof`, which remains a conservative final check that every
contract verifier holds current proof against the whole declared scope. Resolution only
falls back to it for records that carry no binding of their own, and skips computing it
entirely when none do — which is where most of the resolution cost went.

## Where the engine sits in the existing flow

```text
task create -> ready -> claim
   |                      |
   |            assurance plan --compile        (phase A, a forecast)
   |                      |
implement ----------------+
   |
assurance verify  -> reconcile (phase B) -> focused run -> resolve -> escalate -> decide
   |
checkpoint
   |
task complete  -> 2.0 checks first (state, completion proof, checkpoint, integration)
               -> reconcile against the real diff
               -> refuse while mandatory proof debt remains
```

Completion compiles the plan itself, so there is no path — CLI, API or MCP — that reaches
completion without the obligations being derived from the change that was actually made.

## Trust and permissions

| Operation | Who |
|---|---|
| `assurance_status` `_plan` `_explain` `_debt` `_registry` `_integrity` | read-only, offered over MCP |
| `assurance_verify` | a worker holding the task lease; it executes already-approved commands, exactly like `record_evidence` |
| `assurance_compile` `_waive` `_resolve_human` `_register_verifier` `_migrate` `_rollback` | the local project owner only, never offered over MCP |

A worker can discover that more assurance is needed and can run the verifiers it was
authorized to run. It cannot waive a claim, register a capability, record a human verdict,
or change what the engine requires.
