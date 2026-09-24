# Changelog

All notable changes to this project are documented here.

The format is inspired by Keep a Changelog and versions follow Semantic Versioning.

## [Unreleased]

### Added
- **The canonical execution rule, in one source and on every agent surface.**
  `agentic-autonomous-project-execution` now opens with it: when the kit is installed and the
  user asks for implementation, verify operational readiness first; initialise and adopt the
  control plane when that is safe; never continue silently without it while claiming the full
  workflow. It carries the preflight, the request-to-task derivation, the automatic
  checkpoints, verification and completion, and the degraded-mode reporting contract, and it
  compiles to Claude Code, Cursor, Copilot, Windsurf, Antigravity, Gemini, the ChatGPT bundle
  and `AGENTS.md` from that one file. `AGENTS.md` and `MASTER_PROMPT.md` state the same rule,
  with the owner's authorisation for the protected-contract change.
- **Checkpoints, verification and completion without being asked.** `agentic work checkpoint`
  records resumable state at the seven moments worth recording, filling in everything the
  records already hold - the files measured against the tree as it was claimed, the commands
  and results from the evidence since the last checkpoint, the next action from the first
  unproven claim - so a checkpoint cannot disagree with the evidence beside it. `agentic work
  verify` runs what the task declared, which is the project's own gates. `agentic work finish`
  verifies, checkpoints and completes, or returns the refusal as an answer: `VERIFICATION_FAILED`
  for a failing gate, and the completion invariant's own refusal with the outstanding claims for
  proof debt. `agentic work next` names the task whose turn it is.
- **`agentic work start "<request>"`: a request in your own words becomes governed work.**
  The task contract is derived from what is already recorded - the request, the project's
  requirements, its knowledge index, its quality gates, its risk rules and its policy - and
  every field says where it came from. The same request twice is the same task, and a request
  that falls inside open work links to it. Readiness is evaluated, the agent joins and the task
  is claimed, all without a further command. Four decisions stop the request instead of being
  guessed: an undecidable scope, a protected contract in scope, `CRITICAL` risk, and a gate set
  where nothing proves behaviour. A blocked request leaves no task behind. The command
  allow-list is not widened: the project's own required gates are approved and recorded, and
  nothing else. One working tree holds one claim, so a second request is recorded and readied
  while its claim waits.
- **A mandatory execution preflight, `agentic preflight`.** Eight requirements - installation,
  version, control plane, adoption, knowledge, git, quality configuration, task orchestration -
  are checked, whatever can be repaired safely is repaired first, and the result is one of
  three modes: `FULL`, `DEGRADED` or `BLOCKED`. A degraded mode is never implied: the report
  names what is unavailable, whether that is orchestration in a rules-only project or the
  operations that need a commit in a project outside git. `preflight.requires` lets an
  operation refuse a mode it cannot honestly run in, and the same preflight is on the
  versioned API as an owner-only operation.
- **A version check in readiness.** A payload from a newer kit is `BROKEN` rather than
  silently downgraded; one from an older release stops the work and names `migrate`, which
  rewrites generated files and so stays with the owner; leftovers from the pre-`.agentic`
  layout are reported as drift with `migrate --prune`, because deleting files is never
  automatic.
- **`agentic-discipline repair`: safe auto-repair with an audit record.** It reinstalls a
  pruned payload, recompiles stale agent surfaces, initialises a missing control plane and
  reindexes a project that has drifted, in dependency order, and writes what it did to the
  audit chain as `readiness.repair`. A repair qualifies only when it cannot lose data, change
  what the project is supposed to do, reach outside the machine, or write anything but the
  files the kit itself owns; the payload is filled in rather than overwritten. An unexplained
  control directory, an altered audit chain and a plane adopted for another checkout are
  reported and never repaired, and a repair whose cause is still open is not attempted.
- **`init` leaves the project operational, not merely configured.** After the contracts and
  the adapters it initialises the control plane, indexes the project and measures readiness,
  so one command produces a repository that can run the workflow and a closing line that
  reports what the checks found. Every phase is idempotent: a second run keeps the state
  database with its tasks, leases, checkpoints and evidence, and only brings the index up to
  date. An unexplained `.agentic/control/` and a `--rules-only` on an adopted project are
  refused with their reason rather than resolved. `--rules-only` records the choice,
  `--no-adopt` skips adoption for one run, and `--adopt` turns it on; a recorded choice
  survives ordinary re-runs. `init` exits nonzero when what it leaves behind is not usable.
- **One readiness model, and a `doctor` that reports the truth.** Installation health,
  project health and execution readiness are three separate questions, so a repository with
  every discipline installed and no control plane no longer reports PASS. Nine checks, each
  with the reason it is not met and the command that repairs it, resolve to one of `READY`,
  `PARTIAL`, `DEGRADED`, `BROKEN` or `NOT_INITIALIZED`. An index that has fallen behind the
  tree is reported as drift, not as a gap, so the check does not turn red on every edit.
  `doctor` prints a table by default and keeps its machine report under `--json`, where the
  2.0 fields are unchanged and a `readiness` block is added.
- **Agentic Discipline 2.1 - the Adaptive Assurance Engine.** A change now creates proof
  obligations, and a task completes only when every mandatory one is resolved by current
  evidence. The agent no longer declares success; the state of its obligations decides what
  it may claim and whether the work advances. Guide: [docs/v2.1/README.md](docs/v2.1/README.md).
  - **Proof obligations** as first-class records: one concrete claim each, with the
    requirement, acceptance criterion, policy or dependency it came from, the capabilities
    that could discharge it, the verifiers selected, the paths and symbols it depends on,
    and its criticality. Identity is derived from the task and the origin, so recompiling a
    plan updates obligations rather than duplicating them.
  - **An assurance compiler** that derives them deterministically from the task contract and
    from repository policy applied to observed paths, using the same risk signals
    `agentic-discipline risk` already uses. It compiles twice: a forecast from the declared
    scope before implementing, and the enforced plan from the diff the task actually made.
  - **Expansion without contraction.** A recompile may add obligations, widen their paths,
    raise their criticality or deepen the route they require. It can never drop one, make a
    mandatory claim optional, lower a criticality or leave a claim with no verifier; the
    refusal is recorded on the plan and written to the audit chain. The only sanctioned
    contraction is an owner waiver with a reason and an authority, and it is refused while
    current evidence refutes the claim.
  - **A verifier capability registry** so the planner reasons about what a verifier proves,
    how strong that proof is and what it costs, instead of about tool names. Projects can
    register their own kinds. The task contract keeps supplying the concrete argv.
  - **A proof planner** that takes the cheapest sufficient route, prefers a falsifying
    strategy among equally cheap ones, and never lets agent judgment stand in for a
    deterministic verifier that can reach the claim - at selection and again at resolution.
  - **Progressive assurance**: a route that reaches no verdict escalates to a deeper one,
    which replaces it; the superseded verdict stays in the ledger and never counts as proof
    again. Depth only rises. A plain failure means repair, and staleness means rerun.
  - **Per-obligation freshness.** Each claim binds to the paths, requirement versions,
    protected tree, acceptance text, verifiers, claim text and policy it depends on, so an
    unrelated edit no longer invalidates it and a relevant one always does. Restoring a file
    byte for byte restores the claim: freshness is content, not history.
  - **Conflicts and unknowns that cannot become passes.** Current evidence is read together,
    so one fresh failure beside a fresh pass is `CONFLICTED` whichever ran last; a verifier
    that could not reach a verdict is `BLOCKED`; a claim no declared verifier reaches is
    `UNKNOWN`. A verdict is checked against its own hashed artefact, so editing the stored
    row to say `PASS` does not restore a claim the run failed.
  - **Proof debt** as a count of open claims - never a confidence score - readable by task,
    requirement and criticality.
  - **An assurance decision**: `CONTINUE`, `REPAIR`, `EXPAND_VERIFICATION`, `BLOCK`,
    `ESCALATE`, `HUMAN_REQUIRED` or `COMPLETE`, from the obligation states plus risk,
    protected paths and the authority the task contract still grants.
  - **Human-required claims** that produce a concrete request - the claim, what to inspect,
    what already passed automatically, what judgment is left - and record the verdict as
    `HUMAN` evidence bound to the artefacts it judged, so it goes stale when they change.
  - **`agentic assurance`**: `plan`, `verify`, `status`, `explain`, `debt`, `registry`,
    `integrity`, and the owner actions `waive`, `resolve`, `migrate` and `rollback`. The
    same operations are on the versioned API, the read and verify ones over MCP, and a
    read-first assurance view in the console. One application layer behind all of them.
  - **The completion invariant.** `task complete` reconciles the plan against the real diff
    and refuses a task holding mandatory proof debt - on every interface, tested on all four.
  - **An explicit, idempotent, reversible migration.** Schema 2 exists alongside schema 1, so
    a 2.0 project keeps its exact behaviour until an owner runs `agentic assurance migrate`.
    Legacy evidence keeps its artefacts and gains legacy provenance rather than a
    relationship nobody measured. See [docs/v2.1/MIGRATION.md](docs/v2.1/MIGRATION.md).
  - **A scoped mutation harness**, `scripts/assurance_mutation.py`, with a baseline control,
    a journal, resume over identical sources, and a gate against reviewed dispositions in
    `docs/v2.1/evidence/mutation-dispositions.json`.

### Changed
- **`agentic-discipline init` makes the project operational by default.** It used to install
  the rules and leave the control plane to a separate `agentic adopt`. For the previous
  behaviour, pass `--rules-only` (recorded) or `--no-adopt` (this run only). Existing
  installations need nothing: the next implementation request, or another `init`, adopts them
  and changes nothing else. See [docs/adoption.md](docs/adoption.md#upgrading-an-existing-installation).
- **`agentic-discipline doctor` prints a table and exits on execution readiness.** The 2.0 JSON
  fields are unchanged under `--json`, with a `readiness` block added. A project whose rules
  are installed and whose control plane is missing now exits nonzero, which is the point.
- One file hasher: `sha256_file` replaces the three copies in the verifier package and the
  inline hashing in the control plane, so evidence artifacts are read in chunks rather than
  loaded whole.
- Fewer repeated reads of the same thing: `binding` reads the policy once, `check_changes`
  resolves the workspace once, `_index` walks the knowledge graph once, `claim` scans the
  leases once, and `claim`, `refresh_workspace` and `merge_workspace` measure the tree once
  instead of hashing it again for each record. `refresh_workspace` and `merge_workspace` now
  store exactly the tree their checks accepted. Measured on the 1,000-file fixture, the
  timings are unchanged.

### Fixed
- A test run's own output files are no longer treated as project content. Running a coverage
  gate wrote `.coverage` into the tree, which counted as a change outside the task's scope and
  failed the task for a file nobody wrote; the same churn moved the tree fingerprint, so
  evidence elsewhere went stale for the same reason. Coverage data and `htmlcov/` are now
  excluded from discovery, beside the caches that already were.
- A complete installation is twelve disciplines, not eleven. The expected count was one
  short, so a project missing a discipline reported a healthy installation; it now reports
  `STALE`, which `agentic-discipline init --force` repairs.
- Recompiling an unchanged plan no longer writes a new revision of every obligation and
  reports it as widened. The merge added a depth field the stored obligation did not carry
  yet; the depth is now recorded when the obligation is created. Found by the scoped
  mutation campaign, which also added the isolated test the completion invariant lacked.
- A `unit` verifier no longer counts as regression proof. The capability registry declared
  `unit` as supplying `regression`, which let a unit suite close a claim about data it never
  examined; the dogfood run on this repository caught it closing a migration-safety claim.
  Capabilities are now narrow: `unit` proves unit behaviour, and `regression`,
  `historical_stability` and `data_preservation` belong to verifiers that say they examine
  existing behaviour.
- `init` now adds `.agentic/control/` to the `.gitignore` block it manages. The control
  plane's SQLite state, its hash chain and its session hashes were left for a project to
  commit by accident, although the documentation said not to.
- `init` repairs an older block instead of skipping it. A project adopted before a release
  that added a rule kept a block without it, so running `init` again was no upgrade path;
  the command now adds only the rules the file is missing, inside the block it owns, and
  names them in its report (`UPDATE .gitignore (added .agentic/control/)`). A rule the
  project already ignores elsewhere is not repeated, and the rest of the file is untouched.
- `init` writes `.gitignore` with the line endings the file already uses. Running it on
  Windows rewrote a whole LF file as CRLF, which showed up as an all-lines diff.
- `docs/compatibility.md` listed one generated file per tool; the compiler writes one per
  discipline, named `agentic-<id>`.
- `docs/install.md` pinned the composite action to `@v1`, a tag that does not exist.
- `docs/IMPLEMENTATION_STATUS.md` still described the release as pending, and `GITHUB_SETUP.md`
  still explained the first push of a repository published since 1.1.0.
- `docs/v2/evidence/README.md` now says which run produced each artifact and which ones a
  later run superseded.

## [2.0.0] - 2026-09-19

### Added
- Agentic Discipline 2: a persistent local project control plane (Python and SQLite)
  exposed as the `agentic` command, alongside the unchanged `agentic-discipline` command.
  - Project knowledge with provenance, history, retirement and conflicting-claim detection.
  - Task contracts, expiring leases and checkpoints another agent can resume from.
  - Verification evidence bound to the exact inputs it checked, which goes stale when they
    change, so completion cannot rest on a run of older files.
  - Isolated Git worktrees for parallel work, fast-forward integration, and recovery from a
    merge that succeeded in Git but not in the database.
  - A command line, a versioned API, a stdio MCP server and a read-first local console.
  - Explicit import from a v1 installation, with dry run, backup and rollback.

  The control plane ships in every distribution: the Python package, the standalone executables
  (each archive now holds `agentic` beside `agentic-discipline`) and the npm launcher, which adds
  an `agentic` command (`npx -p agentic-discipline agentic`). `agentic --version` reports the
  package version. It is stable within the single-user, local trust boundary in
  `docs/v2/LIMITATIONS.md`.
- Mutation testing in CI, with an outcome gate that fails while any mutant is unresolved.
  `docs/v2/MUTATION_EXEMPTIONS.md` records each survivor proven to change nothing observable,
  with the check that proves it.
- A reviewed exception list for the mutation gate, `policies/mutation-exceptions.json`, on a
  protected path. Each exception names the function and the exact line a mutant changes, before
  and after, with its family and reason, so it survives mutmut renumbering. The gate accepts a
  survivor only through an exact match, and fails on any exception that no longer matches one.
  CI names the list through the gate step's `MUTATION_EXCEPTIONS` environment variable.
- The mutation gate proves four families of equivalent survivors mechanically and stops
  counting them: SQL keyword or identifier case, codec name case, the `typing.cast` type
  argument, and pattern case under `re.IGNORECASE` (the codec rule also reads the codec passed
  to `.encode()` and `.decode()`). The original and the mutant must differ in
  exactly one place that satisfies the rule; each accepted mutant is listed with its rule, and
  every other survivor still fails the gate.
- `agentic-autonomous-project-execution`, a twelfth canonical discipline for continuous
  execution of authorized software plans, task-level blocker isolation, bounded repair
  attempts, resumable status, and evidence-backed completion. All agent adapters and
  Python distributions include it from the same source.
- `/execute` in the generated Claude Code plugin and short English/Spanish project
  prompts. Autonomous execution preserves protected contracts, risk gates, and the
  user's scope and authorization.

### Changed
- The npm launcher publishes over OIDC trusted publishing instead of a stored `NPM_TOKEN`. Requires a
  trusted publisher registered on the npm package (GitHub Actions, this repository, `release.yml`,
  environment `npm`), which npm only allows once the package exists - so the first release still had
  to publish with a token. Node moves to 22 and npm to 11.5.1 or later, the versions that understand
  OIDC; `--provenance` is dropped because trusted publishing attests provenance on its own.
- `integrity` no longer fails on a test or assertion removed together with the code it called,
  when nothing in the repository defines that code any more; deleting a feature with its tests
  could never pass the audit. Such tests are listed under `retired_tests` instead.

### Removed
- macOS standalone builds, and the npm launcher's macOS and Linux ARM64 downloads. CI does not
  run the test suite on macOS, and no Linux ARM64 build was ever produced, so the launcher
  requested assets that were untested or missing. On those platforms it now says to install with
  `pipx install agentic-discipline-kit`.
- The `bootstrap` command, the `bootstrap_project` function and `scripts/bootstrap_project.py`.
  They were compatibility aliases for `init`; use `agentic-discipline init --target <path>`, with
  `--profile <id>` where `--stack <id>` was passed.
- The compatibility scripts `scripts/acceptance_compile.py`, `crap_score.py`,
  `integrity_audit.py`, `protected_paths.py`, `quality_engine.py` and `risk_score.py`. Each ran
  one command of the CLI: `compile-acceptance`, `crap`, `integrity`, `protected`, `quality` and
  `risk`.

### Fixed
- The evidence ledger lock no longer fails with `PermissionError` on Windows when a writer
  releases the lock at the moment another acquires it; a vanished lock is retried a bounded
  number of times while genuine permission failures still surface.
- `integrity` charged the lines of a deleted file to the file listed before it, so deleting a
  whole test file after a source file removed its tests and assertions unreported.
- Output of git, quality gates and verifiers is read as UTF-8, with undecodable bytes replaced.
  It was read in the locale's encoding: on Windows, UTF-8 output came back garbled and a byte the
  code page cannot map crashed the read, so `integrity` failed on such a diff instead of auditing
  it; on any platform, a tool printing invalid UTF-8 crashed its gate or verifier the same way.
  The control plane's file discovery read non-ASCII paths the same way on Windows.
- Three installed playbooks told agents to run `risk_score.py`, `scripts/quality_engine.py` and
  `scripts/integrity_audit.py`, which `init` never copies into a project. They now name
  `agentic-discipline risk`, `quality` and `integrity`.
- Verifier contracts and quality gates judge `working_directory` by POSIX and Windows rules
  together. A verifier validated on Linux accepted `C:\x`, `\\server\share` and `..\x`, and one
  validated on Windows accepted `/tmp/x`; each leaves the project on the other platform. Paths
  with a drive such as `C:x` and root-relative Windows paths such as `\x`, which both platforms
  accepted, are now rejected as well.
- Task contract scope and verifier input paths are parsed as POSIX paths on every platform. On
  Windows `/etc/x` was not considered absolute and was accepted; such a task could not change
  anything outside the repository, but its contract is now rejected as on Linux.
- A verifier that timed out on Linux or macOS recorded its partial output as a Python bytes
  literal such as `b'started'`, untrimmed, because that output arrives as bytes there even when
  text was requested. It is now decoded and trimmed like any other output.
- `hygiene` missed a fallback written across several added lines, because each added line was
  searched on its own. Consecutive added lines are now searched together.
- Plan audit reported fields the task contract allows to be empty (`out_of_scope`,
  `dependencies`, `boundaries`, `context`) as missing when a plan stated them as empty lists.
- The integrity audit no longer reports generated evidence or runtime counters as changes to a
  quality gate.

## [1.1.0] - 2026-09-06

### Migration required for existing installations

`init` now installs its payload under `.agentic/` instead of the repository root. Existing
installations keep working, but the old root copies of `skills/`, `policies/`, `schemas/`,
`templates/`, `config/risk-weights.json` and `MASTER_PROMPT.md` become stale duplicates. Move them
with `agentic-discipline migrate --to 3.0`, review
`artifacts/payload-migration-report.json`, then remove the legacy copies with
`agentic-discipline migrate --to 3.0 --prune`.

### Added
- Multi-tool skill compiler: every agent surface is emitted in the format its tool actually loads -
  Claude Code and Antigravity skills with `name`/`description`, Cursor `.mdc` rules with `globs`,
  Copilot `.instructions.md` with `applyTo`, Windsurf rules with trigger modes, `GEMINI.md`, and
  `AGENTS.md` for Codex, Zed, Cline, Aider and Jules.
- Canonical activation metadata on all eleven disciplines, split into `description` (what the
  discipline does) and `when_to_use` (when it applies), so a tool can decide when to load each one.
  Formats with a single description field receive both halves combined, keeping selective activation.
- `argument-hint` on every generated slash command, so the host shows the expected argument while
  the user is typing.
- `npx agentic-discipline init`: zero-install entry point that needs neither Python nor a `PATH` setup.
- Installable Claude Code plugin with the `/spec` to `/retro` lifecycle as slash commands, generated
  from the canonical disciplines and guarded against drift by a test.
- ChatGPT export bundle for Projects and Custom GPTs, where no project filesystem exists.
- `--dry-run` on `init` and `adapters sync`; `adapters list`; `--json` for machine-readable output.
- `migrate --prune` to remove the legacy root payload after it is reinstalled under `.agentic/`.
- PyPI trusted publishing and npm publication in the release workflow.

### Changed
- `init` installs the payload under `.agentic/`; only `AGENTS.md` and `agentic.config.json` are added
  to the repository root, down from fifteen top-level entries.
- Generated gates that cannot run in the repository are written with `required: false` and a `note`
  explaining why, instead of failing on first use.
- `init` and `adapters sync` print a human summary by default.
- The 20 workflow playbooks install to `.agentic/playbooks/` as reference for the eleven disciplines,
  resolving the overlap between the two sets.
- Phase directories are created on demand rather than pre-created with `.gitkeep` files.

### Fixed
- Adapters emitted one byte-identical file to every tool path, so Claude Code, Cursor, Windsurf and
  Antigravity never registered the disciplines as skills or rules at all.
- `parse_frontmatter` now unquotes values, making a render/parse round trip lossless.

## [1.0.0] - 2026-08-29

### Added

- Verification-native runtime with verifier contracts, registry, deterministic execution, normalized results, sensitivity states, and protected metadata hashes.
- Canonical disciplines and `.agentic` project payload installed by `agentic-discipline init`.
- Idempotent vendor adapter synchronization, migration reports, and evolution hygiene checks.
- Verifier, adapter, migration, and hygiene CLI commands.

## Pre-release development

The following capabilities were built during private development and first shipped publicly in
1.0.0.

### Verification foundation

- Fail-closed quality configuration validated by JSON Schema.
- Typed requirement-graph validation and complete evidence-path checks.
- Strict Acceptance IR compilation and schema validation.
- Hash-chained, concurrency-safe evidence ledger with verification command.
- Packaged bootstrap command and wheel smoke testing.
- Cross-platform CI, protected-contract enforcement, security audit and build provenance.

### Workflow improvements

- `doctor` now verifies Git, contracts, schemas and quality configuration.
- Risk classification can use external weights and fail CI at a configured level.
- Integrity auditing detects removed tests/assertions and disabled workflows.
- Production contracts, workflows and executable configuration are protected boundaries.

### Engineering lifecycle foundation

- 20-skill engineering lifecycle.
- Requirement graph.
- Acceptance IR/compiler.
- Risk classification.
- Property-testing skill.
- CRAP analysis.
- Metric-aware quality gates.
- Differential mutation workflow.
- Integrity / anti-gaming audit.
- Independent reviewer protocol.
- Evidence ledger.
- Agent retrospective memory.
