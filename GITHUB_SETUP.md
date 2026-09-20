# GitHub settings

Repository settings cannot be committed as files, so they are recorded here. This is
what the repository is configured with, and what a fork or transfer should reproduce.

## Description and topics

> Evidence-backed engineering controls, quality gates, and protected contracts for AI coding agents.

```text
ai-agents
agentic-coding
software-engineering
quality-gates
mutation-testing
acceptance-testing
software-quality
developer-tools
```

## Enable

- Issues
- Discussions, if you want community Q&A
- Private vulnerability reporting
- Dependabot alerts
- Dependabot security updates
- Code scanning
- Dependency graph, which `Security / dependency-review` needs

## Default branch ruleset

For `main`:

- require pull requests;
- require at least one approval;
- dismiss stale approvals;
- require all conversations to be resolved;
- require status checks before merge;
- block force pushes;
- block deletion.

Recommended required checks, by the name each one reports:

```text
CI / lint
CI / typecheck
CI / test (ubuntu-latest, 3.12)
CI / test (windows-latest, 3.12)
CI / package
CI / repository
CI / mutation
Agentic Integrity / guardrails
Security / dependency-review
Security / codeql
Security / python-security
```

`CI / mutation` can be required since every survivor is either killed, proven equivalent
by a gate rule, or accepted through the reviewed list in
`policies/mutation-exceptions.json`. A new survivor fails it.

`Agentic Integrity / guardrails` fails by design on a pull request that changes a
protected path, which is the signal to review that change rather than a defect.

If the repository is transferred or forked, update `.github/CODEOWNERS` with a user or team that has
write access. Require Code Owner approval for protected-contract and workflow changes.

## Releases

Semantic versioning; the current release is `v2.0.0`. Pushing a `v*.*.*` tag runs
`release.yml`, which builds the Python distribution and an SBOM, builds and smoke-tests
the `agentic-discipline` and `agentic` executables for Linux and Windows, and publishes:

| Target | How it authenticates |
|---|---|
| PyPI | Trusted publishing: register this repository, `release.yml` and the `pypi` environment as a publisher |
| npm | OIDC trusted publishing from the `npm` environment; no token is stored |
| GitHub release | The workflow's own token, uploading every built asset |

Both publish jobs are safe to re-run: PyPI skips files it already has, and npm returns
early when the registry already holds that version.
