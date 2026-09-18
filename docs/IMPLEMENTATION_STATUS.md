# Implementation Status — Agentic Discipline 2 preview

## Completed

The local control plane is implemented alongside the existing v1 toolkit. The table
records executable preview behavior; it does not certify every future scale target
or grant release approval. Detailed limitations are in `v2/LIMITATIONS.md`.

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

## In Progress

- Mutation survivor disposition based on the complete CI campaign; selected local retest was interrupted and is marked partial.
- Performance fixture now meets all targets after independently reviewed discovery optimization.
- Final focused independent review is closed; the integrated local suite has 1344 passing tests.
- GitHub CI verification of the integration commit is pending.

## Pending

- P27 release certification: supported platform matrix, required review/acceptance and
  release evidence. No stable 2.0 version or distribution has been published.

## Blockers

- Latest full CI mutation run (35239651553, 4705c58) has 657 unresolved survivors and no timeouts (down from 5,326 on the first measured run); the strengthened CI outcome gate fails explicitly until they are resolved. Mutants proven to change nothing observable are recorded with their proof in docs/v2/MUTATION_EXEMPTIONS.md; the gate does not read that file and fails on them too.
- Final human review is required by the repository's trust-boundary/release policies.

## Technical Debt

- External network/cost enforcement requires host isolation and metering; the local
  process runner measures runtime, retries, file/line budgets and contract permissions.
- Large multi-task repositories need measured caching before claiming the same latency
  bounds as the recorded single-task 1,000-file fixture.
- Non-Python symbol/call resolution is not implemented; those languages use bounded
  file observations and existing profiles. Runtime understanding remains evidence-based.

## Deviations

- Implement the supplied plan as a modular Python/SQLite local preview, reusing the
  working v1 executor and diagnostics; no TypeScript rewrite or hosted LLM dependency.
- Plan audit consumes executable structured contracts. The coding agent resolves prose
  and missing business intent using the documented ask-last ladder.
- Detailed P00–P27 IDs are used; the short roadmap groups multiple phases.
- The package remains at the existing release version until release approval.

## Next Tasks

Finish the recorded hardening/review gates, wait for CI on the integration commit,
then run the repository's release process.
