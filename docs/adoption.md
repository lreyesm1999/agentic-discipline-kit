# Adoption Guide

## Zero-configuration start

Run `agentic-discipline init` from the repository root. The command detects included project profiles,
supports mixed repositories, and falls back to a generic command-based configuration when the stack
is unknown. Review the generated gates before making them blocking in CI.

Adopters can use a standalone executable, the container image, or the repository's GitHub Composite
Action; Python is only required when installing the CLI from source.

The container image contains the Agentic Discipline CLI, not every possible project toolchain. For
Node, .NET, or other ecosystems, derive a project image with those tools installed, or use the
Composite Action so gates run directly on the hosted runner.

## Greenfield repository

Start with the default thresholds and all protected paths enabled.

## Legacy repository

Do not make adoption impossible by demanding an instant perfect baseline.

Use a ratchet:

1. Record baseline metrics.
2. Require changed code to meet stronger targets.
3. Prevent repository-level regression.
4. Remove exclusions over time.
5. Move optional gates to required as tooling stabilizes.

## CI rollout

Recommended phases:

1. report-only risk and integrity;
2. blocking protected-path and unit gates;
3. blocking coverage/type/lint/build;
4. architecture and security;
5. differential mutation on high-risk paths;
6. independent review policy for HIGH/CRITICAL changes.

## Human approval

Keep explicit human approval for changes involving irreversible operations, regulated workflows,
high-value financial behavior, safety-critical behavior, or organizational policy.
