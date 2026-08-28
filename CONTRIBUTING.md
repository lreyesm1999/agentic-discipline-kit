# Contributing

Thank you for improving Agentic Discipline Kit.

## Development setup

```bash
python -m pip install -e ".[dev]"
pre-commit install
make check
```

## Branches

Use short topic branches:

```text
feat/acceptance-adapter-go
fix/integrity-parser
docs/risk-policy
```

## Commits

Use Conventional Commit-style messages where practical:

```text
feat: add Go acceptance adapter
fix: detect disabled mutation scope
docs: clarify critical release policy
test: cover requirement graph edge case
```

## Pull requests

A PR should be focused and should explain:

- problem and intent;
- behavior changed;
- tests/evidence;
- risk;
- compatibility impact;
- whether protected contracts changed.

Do not mix unrelated refactoring into behavioral changes.

## Tests

All changes to deterministic tooling should include tests. Bug fixes should add a regression test
where practical.

Run:

```bash
make check
```

before opening a PR.

## Protected framework contracts

Changes under `policies/`, `schemas/`, `AGENTS.md`, or the semantics of a `SKILL.md` should receive
extra review because they change how downstream agents are governed.

## Security

Do not open public issues for vulnerabilities. Follow `SECURITY.md`.
