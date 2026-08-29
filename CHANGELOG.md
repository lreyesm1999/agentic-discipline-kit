# Changelog

All notable changes to this project are documented here.

The format is inspired by Keep a Changelog and versions follow Semantic Versioning.

## [Unreleased]

### Added
- Zero-configuration `init` command with manifest-based project detection.
- Composable multi-stack quality configuration with safe per-gate working directories.
- Data-driven custom project profiles and a generic fallback for unknown ecosystems.
- Standalone Windows, macOS, and Linux release builds, a container image, and a GitHub Composite Action.

### Changed
- `bootstrap --stack` is retained as an optional compatibility alias instead of a fixed stack whitelist.
- Python remains an internal/source-development runtime and is no longer required by standalone users.

## [2.1.0] - 2026-08-28

### Added
- Fail-closed quality configuration validated by JSON Schema.
- Typed requirement-graph validation and complete evidence-path checks.
- Strict Acceptance IR compilation and schema validation.
- Hash-chained, concurrency-safe evidence ledger with verification command.
- Packaged bootstrap command and wheel smoke testing.
- Cross-platform CI, protected-contract enforcement, security audit and build provenance.

### Changed
- `doctor` now verifies Git, contracts, schemas and quality configuration.
- Risk classification can use external weights and fail CI at a configured level.
- Integrity auditing detects removed tests/assertions and disabled workflows.
- Production contracts, workflows and executable configuration are protected boundaries.

## [2.0.0] - 2026-08-28

### Added
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
