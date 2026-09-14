# Changelog

All notable changes to this project are documented here.

The format is inspired by Keep a Changelog and versions follow Semantic Versioning.

## [Unreleased]

### Added
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

### Fixed
- The evidence ledger lock no longer fails with `PermissionError` on Windows when a writer
  releases the lock at the moment another acquires it; a vanished lock is retried a bounded
  number of times while genuine permission failures still surface.

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
