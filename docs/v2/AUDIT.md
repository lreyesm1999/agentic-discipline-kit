# AD2 audit and implementation decision

Baseline: 783355fcc07e2fea5a2d69e9c169f9dbb1adf976 plus autonomy proposal
c4c3d528478e7f1a307fb477e092b4b09b10cf66. The user-supplied plan is preserved
under `plan/`. Track P00–P27; the shorter stage roadmap groups several phases.

| Capability | Existing source | Disposition |
|---|---|---|
| Host adapters and disciplines | adapters.py, skills.py | Reuse |
| Stack/profile detection | profiles.py | Reuse, extend per-file coverage |
| Installation and migration | bootstrap.py, migration.py | Preserve v1; isolate AD2 state |
| Requirement graph | requirements.py | Validate and import with provenance |
| Deterministic verification | quality.py, verifier/ | Reuse; bind executions to tasks |
| Evidence ledger | evidence.py | Preserve API; add transactional DB audit |
| Risk, protected contracts, integrity | risk.py, policies/, integrity.py | Preserve |
| Knowledge history, typed graph, FTS | None | New application services |
| Tasks, context, checkpoints, leases | None | New transactional services |
| Workspaces, reconciliation, budgets | None | New local control plane |
| MCP and console | None | Interfaces over the same services |

## Architecture decision

Use Python >=3.11 and SQLite WAL, foreign keys, optimistic versions, FTS5 and
hash-linked audit in a modular monolith under `agentic_discipline.control`.
Add an `agentic` entrypoint while retaining all existing CLI meanings.
TypeScript rewrite, graph databases and microservices add no demonstrated value.
The initial trust boundary is the local OS user; distributed/hosted tenancy is
outside the plan's initial local architecture.

## Gaps and resolutions

- Existing bootstrap may overwrite generated adapters or relax initially unavailable
  gates. AD2 adoption writes only isolated state and never runs discovered commands
  implicitly or overwrites project instructions/configuration.
- Prose does not define executable acceptance. Require structured task contracts and
  explicitly reviewed command arrays; report gaps for narrative plans.
- The diff auditor flags replaced assertions. Preserve it and record findings for
  human review rather than weaken the check.
- Stable release requires the repository's human review and CI gates. Implementation
  can proceed without claiming that release has occurred.

## Research provenance

The supplied plan is the design input. No external project's code or prompts have
been copied. Protocol documentation is cited in interface documentation.
