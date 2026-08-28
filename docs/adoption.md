# Adoption Guide

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
