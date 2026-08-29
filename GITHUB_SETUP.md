# GitHub Setup

The repository content is ready to push. GitHub-side repository settings cannot be committed as
normal files, so configure them after the first push.

## First push

Create an empty GitHub repository, then run:

```bash
git init
git add .
git commit -m "chore: initial Agentic Discipline Kit v2 repository"
git branch -M main
git remote add origin <repository-url>
git push -u origin main
```

## Recommended repository description

> Evidence-backed engineering controls, quality gates, and protected contracts for AI coding agents.

## Recommended topics

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

## Default branch ruleset

For `main`:

- require pull requests;
- require at least one approval;
- dismiss stale approvals;
- require all conversations to be resolved;
- require status checks before merge;
- block force pushes;
- block deletion.

Recommended required checks:

```text
CI / lint
CI / typecheck
CI / test
CI / package
Agentic Integrity / guardrails
Security / dependency-review
Security / codeql
```

Before the first push, replace the placeholder owner `@agentic-discipline-maintainers` in
`.github/CODEOWNERS` with a real user or team that has write access. Require Code Owner approval for
protected-contract and workflow changes.

Mutation testing runs on Linux because current Mutmut releases require operating-system `fork`
support. Keep `CI / mutation` required for changes to the deterministic Python core.

If a GitHub plan or private-repository configuration does not provide dependency review or CodeQL,
adjust the required checks to the security capabilities available to that repository.

## Release convention

Use Semantic Versioning. The first public release is:

```text
v1.0.0
```

The included release workflow builds the Python distribution when a `v*.*.*` tag is pushed.
