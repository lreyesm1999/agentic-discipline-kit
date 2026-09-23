# Implementation Status — Agentic Discipline 2 and 2.1

## Completed

The local control plane is implemented alongside the existing v1 toolkit. The table
records executable behavior as released in 2.0.0; it does not certify every future
scale target. Detailed limitations are in `v2/LIMITATIONS.md`.

| Plan phases | Implemented behavior | Deterministic evidence |
|---|---|---|
| P00 | Existing-capability audit, original plan and reuse decisions | `v2/AUDIT.md`, `v2/plan/` |
| P01–P03 | Stable IDs, provenance, typed links, versions, SQLite WAL/CAS, audit, FTS, historical queries | `test_kernel.py`, `test_governance.py` |
| P04–P05 | Bounded discovery, qualified Python symbols, containment, coverage, atomic/idempotent adoption, exclusion of recognized secrets | `test_execution.py`, `test_resilience.py`, `test_review_regressions.py` |
| P06–P08 | Claim authority/conflicts, owner resolution, structured plan audit and dependency/readiness checks | `test_kernel.py`, `test_governance.py` |
| P09–P12 | Validated contracts, state transitions, untruncated mandatory context, checkpoints, cross-agent resume | `test_execution.py`, `test_governance.py`, `test_interfaces.py` |
| P13 | Real execution artifacts, hashes, source/requirement/constraint binding, complete proof and stale/dependent invalidation | `test_execution.py`, `test_resilience.py`, `test_review_regressions.py` |
| P14–P18 | Agent capabilities, atomic leases, bounded run recovery, worktrees, conservative parallelism, rebase/merge and interrupted-merge recovery | `test_workspaces.py`, `test_resilience.py`, `test_review_regressions.py` |
| P19–P22 | External-edit reconciliation, retirement/history, contract budgets, protected paths, current metrics and activity | `test_governance.py`, `test_review_regressions.py`, real status API |
| P23–P24 | Versioned CLI/API, stdio MCP and read-first localhost console | `test_interfaces.py`, real HTTP and installed-wheel checks |
| P25–P26 | Failure injection, property tests, own-repository execution and 1,000-file benchmark | `test_resilience.py`, `v2/evidence/dogfood.json`, `v2/evidence/benchmark.json` |
| P27 implementation | Explicit legacy import, dry-run, backup, rollback, package compatibility and operational documentation | `test_interfaces.py`, `test_governance.py`, `v2/evidence/wheel-smoke.json` |

## Released

- 2.0.0 ships the control plane in the Python distribution, the standalone executables
  and the npm launcher. `v2/VALIDATION.md` records the executed release gates.
- The integrated suite has 1,605 passing tests on Linux, and CI runs it on Linux and
  Windows with Python 3.11, 3.12 and 3.13.
- The mutation gate passes: CI run 35443136819 killed 15,214 of 15,425 mutants, proved
  102 survivors equivalent by rule and accepted 109 through the reviewed exceptions in
  `policies/mutation-exceptions.json`, leaving none unresolved.

## Agentic Discipline 2.1 — the Adaptive Assurance Engine

Implemented alongside 2.0 and inactive until a project is migrated on purpose, so an
existing 2.0 installation behaves exactly as it did. The table records executable behaviour
with the evidence that demonstrates it; detailed limits are in `v2.1/LIMITATIONS.md` and
the engine is described in `v2.1/README.md`.

| Dependency phase | Implemented behaviour | Deterministic evidence |
|---|---|---|
| P01 domain model | Obligation shape, ten states, capability vocabulary, deterministic identity, monotonic merge that cannot weaken a recorded claim | `test_assurance_units.py`, `test_assurance_properties.py` |
| P02 persistence | Schema 2 beside schema 1, new record kinds on the existing versioned, audited store | `test_store_records.py`, `test_assurance_interfaces.py` |
| P03 compiler | Obligations from the task contract, from repository policy over observed paths, and from what the change reaches; two phases, forecast then enforced | `test_assurance_units.py`, `test_assurance_scenarios.py` |
| P04 registry | What each verifier kind proves, how strong, at what cost and depth; owner-registered project kinds | `test_assurance_units.py` |
| P05 planner | Cheapest sufficient route, falsification first, deterministic dominance, escalation depth | `test_assurance_units.py`, `test_assurance_scenarios.py` |
| P06 runner | Focused execution over the existing `verify()` path, with each run bound to the obligations it was run for | `test_assurance_scenarios.py`, `test_index_and_evidence_records.py` |
| P07 resolver | Per-obligation freshness, conflicts, unknowns, artefact-checked verdicts, proof debt | `test_assurance_units.py`, `test_assurance_failures.py`, `test_assurance_properties.py` |
| P08 invalidation | A claim stales when its own inputs move and survives when they do not; restoring a file restores the claim | `test_assurance_scenarios.py` scenarios 3 and 4 |
| P09 impact | The real diff, its symbols, and the requirements and files it reaches through recorded links | `test_assurance_edges.py`, `test_assurance_scenarios.py` scenario 5 |
| P10 decision | CONTINUE, REPAIR, EXPAND_VERIFICATION, BLOCK, ESCALATE, HUMAN_REQUIRED, COMPLETE, from obligation state plus risk, protected paths and remaining authority | `test_assurance_scenarios.py`, `test_assurance_edges.py` |
| P11 interfaces | CLI group, versioned API, MCP read and verify tools, owner operations withheld from workers, one application layer | `test_assurance_interfaces.py`, `test_api_dispatch.py`, `tests/cli_surface.json` |
| P12 evidence classes | Deterministic, measured, agent judgment and human, with judgment verdicts named as what they are and never able to close a deterministically reachable claim | `test_assurance_scenarios.py` scenario 8, `test_assurance_failures.py` |
| P13 console | Read-first assurance and obligation view over the same read-only API | `test_assurance_interfaces.py` |
| P14 migration | Explicit, idempotent, reversible, with legacy provenance instead of invented relationships | `test_assurance_interfaces.py`, `test_assurance_edges.py` |
| P15 hardening | The twelve acceptance scenarios, property tests over the invariants, failure injection, a scoped mutation campaign, a dogfood run on this repository and measured cost | `v2.1/evidence/`, `v2.1/VALIDATION.md` |

### Deviations from the supplied plan

- The verifier registry lands after the compiler rather than before the planner. The
  compiler needs only the capability vocabulary, and the registry's default declarations are
  easier to justify once the compiler shows which capabilities obligations actually ask for.
- Protected contracts get no obligation of their own. The rule was written, and the dogfood
  run showed it could never fire: the existing change check refuses a protected edit inside a
  task outright, which is a stronger control. It was replaced by the recorded human
  acceptance that the risk policy already requires of CRITICAL work.
- Criticality does not force a verifier depth. Forcing a level-3 route for every CRITICAL
  claim made claims a regression verifier genuinely settles unprovable. Depth required by
  risk is expressed by the compiler adding a falsification obligation for HIGH and CRITICAL
  work instead.
- A focused verification run reports the outcome of what it ran, which is what `VERIFYING`
  has always meant here. An earlier attempt made a partial run claim the task state only when
  full proof held, which turned a successful partial run into `FAILED`. Whether the task holds
  proof for everything is answered by `completion_proof` and by the obligation states, both of
  which completion checks.
- The scoped mutation campaign is a purpose-built harness rather than `mutmut`, which in this
  environment exhausts memory generating mutants for the whole package and deadlocks its
  workers when scoped. The repository-wide `mutmut` gate in CI is unchanged. The harness
  kills 2,135 of 2,163 mutants (98.71%); each of the 28 survivors has a reviewed disposition
  (24 equivalent, 4 POSIX-only), and the harness fails if one is added or goes stale.
- The campaign found three defects the suite had missed, now fixed and pinned: the
  completion invariant had no isolated test, every recompile wrote an unchanged revision
  that reported obligations as widened, and a human verdict's binding was never read back.
- `agentic assurance explain` accepts a task as well as a claim, because the question the
  supplied brief's north star actually asks — why a task cannot complete — is about a task.

### Not implemented

Obligation-level dependencies and budgets, a managed reference-artefact store, a built-in
adversarial reviewer, diff-content signals in the compiler, and a CI mutation gate scoped to
the assurance package. Each is listed with its reason in `v2.1/LIMITATIONS.md` and on the
roadmap.

### Release disposition

2.1 is implemented, tested and documented in this repository. It is **not certified as a
release**. CI run 35906290627 passed the platform matrix and the four mutation shards on
the pull-request diff: 14,837 killed of 14,976, 65 proved equivalent, 74 accepted by
reviewed exception, none unresolved. `guardrails` failed because the branch changes
protected paths. Human acceptance and the version bump from 2.0.0 are still open.
`v2.1/VALIDATION.md` holds the gates and these numbers.

## Technical Debt

- External network/cost enforcement requires host isolation and metering; the local
  process runner measures runtime, retries, file/line budgets and contract permissions.
- Large multi-task repositories need measured caching before claiming the same latency
  bounds as the recorded single-task 1,000-file fixture.
- Non-Python symbol/call resolution is not implemented; those languages use bounded
  file observations and existing profiles. Runtime understanding remains evidence-based.

## Deviations

- Implement the supplied plan as a modular Python/SQLite local control plane, reusing
  the working v1 executor and diagnostics; no TypeScript rewrite or hosted LLM dependency.
- Plan audit consumes executable structured contracts. The coding agent resolves prose
  and missing business intent using the documented ask-last ladder.
- Detailed P00–P27 IDs are used; the short roadmap groups multiple phases.

## Next Tasks

Keep the gate green: a new survivor, or an exception that stops matching a survivor,
fails CI until it is killed or reviewed. macOS becomes a supported platform only once
CI runs the suite there.
