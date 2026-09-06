# Adoption Guide

## Zero-configuration start

Run `npx agentic-discipline init` from the repository root. See the
[install guide](install.md) for every entry point, including the Claude Code
plugin and the ChatGPT bundle.

The command detects included project profiles, supports mixed repositories, and falls back to a
generic command-based configuration when the stack is unknown. Gates whose commands cannot run in
the repository are written non-blocking with the reason recorded in a `note`; review them, wire up
the missing scripts, and promote them to `required` deliberately.

The payload installs under `.agentic/`. Only `AGENTS.md` and `agentic.config.json` are added to the
repository root, which is usually what makes the adoption PR reviewable.

Installing the disciplines needs no runtime at all. The Python CLI is only required for the
deterministic gates, and adopters can use a standalone executable, a container built from the
repository's `Dockerfile`, or the GitHub Composite Action instead of managing it.

No container image is published; the repository ships a `Dockerfile` you build yourself. It
contains the Agentic Discipline CLI, not every possible project toolchain. For
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
