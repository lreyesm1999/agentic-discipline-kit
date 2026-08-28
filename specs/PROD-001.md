# PROD-001 — Production hardening

## Intent

Make Agentic Discipline Kit fail closed, produce tamper-evident verification records, and operate
consistently from source checkouts and installed wheels on supported platforms.

## Requirements

- **FR-001:** Quality configuration must be schema-valid and contain at least one required gate.
- **FR-002:** Required metrics that are missing, invalid, non-finite, timed out, or below threshold
  must prevent a PASS result.
- **FR-003:** Requirement graphs must reject duplicate IDs, missing endpoints, invalid typed
  relations, missing paths when requested, and incomplete evidence traceability at release.
- **FR-004:** Acceptance compilation must reject incomplete scenarios and unsupported syntax rather
  than silently discard behavior.
- **FR-005:** Evidence records must include tool, command, exit code, timestamp and artifact hash,
  form a verifiable hash chain, and serialize concurrent appends.
- **FR-006:** CI must enforce protected contracts, lint, types, tests, coverage, packaging and
  security checks on supported platforms.
- **FR-007:** Doctor must fail outside a Git worktree or when contracts/configuration are missing or
  invalid.
- **FR-008:** A built wheel must contain the contracts and support project bootstrap without a
  source checkout.
- **SEC-001:** Executable gate configuration and CI/workflow files must be treated as protected
  code-review boundaries.

## Non-goals

- Replacing repository permissions or human approval.
- Executing untrusted third-party quality configuration.
- Providing native acceptance adapters beyond the current stack-neutral IR.
