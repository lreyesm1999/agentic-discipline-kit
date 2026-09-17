# Changelog

All notable changes to this project are documented here.

The format is inspired by Keep a Changelog and versions follow Semantic Versioning.

## [Unreleased]

### Added
- Agentic Discipline 2 preview: a persistent local project control plane (Python and SQLite)
  exposed as the `agentic` command, alongside the unchanged `agentic-discipline` command.
  - Project knowledge with provenance, history, retirement and conflicting-claim detection.
  - Task contracts, expiring leases and checkpoints another agent can resume from.
  - Verification evidence bound to the exact inputs it checked, which goes stale when they
    change, so completion cannot rest on a run of older files.
  - Isolated Git worktrees for parallel work, fast-forward integration, and recovery from a
    merge that succeeded in Git but not in the database.
  - A command line, a versioned API, a stdio MCP server and a read-first local console.
  - Explicit import from a v1 installation, with dry run, backup and rollback.

  The control plane ships in the Python distribution only: the standalone executables and the
  npm launcher still start the v1 command. It is a preview, not a stable 2.0 release; its trust
  boundary and limits are in `docs/v2/LIMITATIONS.md`.
- Mutation testing in CI, with an outcome gate that fails while any mutant is unresolved.
  `docs/v2/MUTATION_EXEMPTIONS.md` records the survivors proven to change nothing observable,
  each with the check that proves it, and the survivors deliberately left unkilled; the gate
  does not read that file.
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

### Removed
- The `bootstrap` command, the `bootstrap_project` function and `scripts/bootstrap_project.py`.
  They were compatibility aliases for `init`; use `agentic-discipline init --target <path>`, with
  `--profile <id>` where `--stack <id>` was passed.
- The compatibility scripts `scripts/acceptance_compile.py`, `crap_score.py`,
  `integrity_audit.py`, `protected_paths.py`, `quality_engine.py` and `risk_score.py`. Each ran
  one command of the CLI: `compile-acceptance`, `crap`, `integrity`, `protected`, `quality` and
  `risk`.

### Fixed
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
