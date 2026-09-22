# CLI Reference

This is the `agentic-discipline` command. The project control plane has its own
command, `agentic`, documented in [docs/v2](v2/README.md).

The installed command is:

```bash
agentic-discipline
```

## init

Initializes the current project without requiring a stack selection:

```bash
agentic-discipline init
```

It detects known manifests up to four directories deep, composes all detected profiles, installs the
engineering contracts, and writes `agentic.config.json`. Existing files are preserved unless `--force`
is supplied.

Detection can be overridden or extended:

```bash
agentic-discipline init --profile typescript --profile dotnet
agentic-discipline init --profile-file ./rust-profile.json --profile rust
agentic-discipline init --max-depth 6
```

When nothing is recognized, `init` emits a generic Git-based gate instead of rejecting the project.
See [Project profiles](profiles.md) for the descriptor format.

One run leaves the project operational, not merely configured: after the contracts and the
adapters, `init` initialises the control plane, indexes the project and then measures
readiness, so its closing line is what the checks found rather than a claim.

```text
  Control plane    the repository was adopted and indexed

Status: READY FOR AGENTIC EXECUTION

Next:  ask for the work you want done.
```

Adoption inspects the repository and records state. It does not edit your files, install
dependencies, or run instructions it finds in the tree, and it works outside git as well,
so the order of `init` and `git init` does not matter.

Every phase is idempotent. A second `init` keeps the existing state database with its tasks,
leases, checkpoints and evidence, brings the index up to date, and writes nothing else. Two
cases are refused rather than resolved:

| Situation | What `init` does |
|---|---|
| `.agentic/control/` exists without a state database | installs the rules, leaves the directory untouched, reports `BROKEN`, and exits nonzero. A second database beside the first would split the project's history. |
| `--rules-only` on a project that is already adopted | records nothing and says so. Removing existing state is the owner's decision, never the side effect of a flag. |

For the rules alone, say so explicitly:

```bash
agentic-discipline init --rules-only   # records the choice; readiness reads DEGRADED
agentic-discipline init --no-adopt     # skips the control plane for this run only
agentic-discipline init --adopt        # initialises it on a project installed rules-only
```

A recorded `--rules-only` survives ordinary re-runs: nothing turns orchestration on behind
the owner's back, and `--adopt` is how it is turned on.

`init` exits nonzero when the project it leaves behind is not usable, so a script that chains
it with real work stops instead of continuing half-configured.

The generated configuration is intentionally conservative: it recommends gates but does not install
or execute project dependencies during initialization.

## doctor

Answers three separate questions and never blurs them: whether the kit is installed
correctly, whether this project is under management, and whether the full workflow can
actually run. Rules that nothing enforces are not a passing project, so a repository with
every discipline installed and no control plane now reports what it is.

```bash
agentic-discipline doctor
```

```text
Agentic Discipline status

Installation         PASS
Disciplines          PASS
Agent adapter        PASS
Quality gates        PASS
Control plane        MISSING
Project adoption     MISSING
Knowledge            MISSING
Task orchestration   MISSING
Git integration      PASS

Installation health  PASS
Project health       PARTIAL
Execution readiness  PARTIAL

Reason: Control plane: the control plane has never been initialised here

Outstanding:
- Control plane (MISSING): the control plane has never been initialised here
  Repair: agentic adopt
```

Execution readiness is one of five states:

| State | Meaning |
|---|---|
| `READY` | the whole workflow is available |
| `PARTIAL` | every gap can be repaired without a decision, and each repair is named |
| `DEGRADED` | orchestration is unavailable by the project's own choice, such as a rules-only install |
| `BROKEN` | something needs a human: an altered audit chain, an unreadable database, a control directory with no database, a plane adopted for another checkout |
| `NOT_INITIALIZED` | the kit is not installed here |

The exit code is zero for `READY` and `DEGRADED`, because a recorded choice is not a fault,
and nonzero for the rest.

An index that has fallen behind the working tree is reported as drift rather than as a gap:
it is listed, `agentic reconcile` repairs it, and starting work repairs it anyway, so it does
not by itself make a project less than `READY`.

Options: `--check-tools` probes the executables the gates call, `--json` prints the machine
report (the 2.0 fields plus a `readiness` block), `--fast` skips the working-tree scan that
detects drift, and `--config` points at a specific quality configuration.

## risk

Classifies a git diff.

```bash
agentic-discipline risk --base-ref origin/main --fail-at HIGH
```

## integrity

Checks newly added lines for common quality-gate bypass patterns, and removed lines for deleted
tests, deleted assertions and removed gate configuration.

A removed test or assertion is not a finding when it called code that the same change deletes and
that no tracked file defines any more: such a test can no longer run. It is listed under
`retired_tests` so a reviewer still sees it, and does not fail the audit. A test that also lost an
assertion on code that still exists stays a finding.

```bash
agentic-discipline integrity --base-ref origin/main
```

## protected

Detects edits to protected contract paths.

```bash
agentic-discipline protected --base-ref origin/main
```

## crap

Calculates CRAP from complexity and coverage.

```bash
agentic-discipline crap --complexity 7 --coverage 91 --max 8
```

## compile-acceptance

Creates the stack-neutral Acceptance IR.

```bash
agentic-discipline compile-acceptance \
  --input acceptance/feature.feature \
  --output artifacts/acceptance/feature.ir.json
```

## graph-check

Validates the graph schema, typed edges and orphan requirements. Release verification should add
`--complete` so every requirement must reach evidence.

```bash
agentic-discipline graph-check \
  --graph artifacts/requirements/feature.graph.json \
  --complete --check-paths
```

## quality

Runs configured command gates, extracts configured metrics, and evaluates thresholds.

Commands run directly without a shell. JSON argument arrays are recommended; missing executables,
timeouts, invalid parsers and absent metrics produce deterministic failure/error results.

```bash
agentic-discipline quality --config agentic.config.json
```

## evidence

Adds a hash-chained evidence record containing the measurable command and result.

```bash
agentic-discipline evidence \
  --artifact artifacts/quality-report.json \
  --tool pytest \
  --executed-command "pytest --cov" \
  --exit-code 0
```

## evidence-verify

Verifies sequence, record hashes, hash-chain links and optionally current artifact hashes.

```bash
agentic-discipline evidence-verify --check-artifacts
```

## verify and verifier

`init` installs the current `.agentic/` payload. A verifier package contains `verifier.json` and its
executable entrypoint. The metadata declares the claim, requirement IDs, command, timeout, expected
exit code, dependencies, and sensitivity state.

```bash
agentic-discipline verifier register checks/payment-check
agentic-discipline verifier list
agentic-discipline verifier inspect VER-017
agentic-discipline verifier validate VER-017
agentic-discipline verify VER-017
agentic-discipline verifier protect VER-017
```

Generated verifiers start as `DRAFT`. They must include sensitivity evidence before they can be
protected. Missing commands or environment variables produce `BLOCKED`; an executed failing
condition produces `FAIL`.

## adapters

Synchronize thin vendor projections from the canonical `.agentic` source. Existing user content outside
the managed block is preserved and repeated runs are idempotent.

```bash
agentic-discipline adapters sync
agentic-discipline adapters sync --adapter claude --adapter cursor
```

## migrate

Migrate an earlier internal installation without deleting contracts or evidence. The `3.0` target
names the current internal payload format, not the public package version:

```bash
agentic-discipline migrate --to 3.0
```

The command writes `artifacts/payload-migration-report.json`.

## hygiene

Check evolution lifecycle metadata, unresolved removals, temporary artifacts, and suspicious fallback
additions:

```bash
agentic-discipline hygiene
agentic-discipline hygiene --base-ref origin/main
```

## agentic assurance

The `agentic` control plane's assurance engine: the proof obligations a change creates, the
evidence that currently resolves them, and what the work is allowed to do next. It is
inactive until a project is migrated; see [Agentic Discipline 2.1](v2.1/README.md).

```bash
agentic assurance plan TASK-ID --compile        # compile or reconcile the plan
agentic assurance plan TASK-ID                  # read it: initial, current, what expanded
agentic assurance verify TASK-ID --session-file /private/worker-a.json
agentic assurance status [TASK-ID]
agentic assurance explain PO-ID                  # one claim
agentic assurance explain TASK-ID                # why a task can or cannot complete
agentic assurance debt [TASK-ID]
agentic assurance registry
agentic assurance integrity
```

Owner actions, each requiring its own recorded justification:

```bash
agentic assurance waive PO-ID --reason "..." --authorization "code owner"
agentic assurance resolve PO-ID --decision "..." [--rejected]
agentic assurance migrate [--dry-run]
agentic assurance rollback ASSU-ID --reason "..."
```

`status`, `debt` and `explain` print a plain reading; every action accepts `--json` for the
whole record. `verify` exits 1 when a mandatory obligation is still open, and `integrity`
exits 1 when an invariant is violated.
