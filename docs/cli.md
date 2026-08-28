# CLI Reference

The installed command is:

```bash
agentic-discipline
```

## doctor

Checks Git worktree state, protected contracts, schemas and quality configuration. Add
`--check-tools` to verify configured executables.

```bash
agentic-discipline doctor
```

## risk

Classifies a git diff.

```bash
agentic-discipline risk --base-ref origin/main --fail-at HIGH
```

## integrity

Checks newly added lines for common quality-gate bypass patterns.

```bash
agentic-discipline integrity --base-ref origin/main
```

## protected

Detects edits to protected contract paths.

```bash
agentic-discipline protected --base-ref origin/main
```

## crap

Calculates CRAP from complexity and coverage.

```bash
agentic-discipline crap --complexity 7 --coverage 91 --max 8
```

## compile-acceptance

Creates the stack-neutral Acceptance IR.

```bash
agentic-discipline compile-acceptance \
  --input acceptance/feature.feature \
  --output artifacts/acceptance/feature.ir.json
```

## graph-check

Validates the graph schema, typed edges and orphan requirements. Release verification should add
`--complete` so every requirement must reach evidence.

```bash
agentic-discipline graph-check \
  --graph artifacts/requirements/feature.graph.json \
  --complete --check-paths
```

## quality

Runs configured command gates, extracts configured metrics, and evaluates thresholds.

Commands run directly without a shell. JSON argument arrays are recommended; missing executables,
timeouts, invalid parsers and absent metrics produce deterministic failure/error results.

```bash
agentic-discipline quality --config agentic.config.json
```

## evidence

Adds a hash-chained evidence record containing the measurable command and result.

```bash
agentic-discipline evidence \
  --artifact artifacts/quality-report.json \
  --tool pytest \
  --executed-command "pytest --cov" \
  --exit-code 0
```

## evidence-verify

Verifies sequence, record hashes, hash-chain links and optionally current artifact hashes.

```bash
agentic-discipline evidence-verify --check-artifacts
```

## bootstrap

Installs the contracts and a stack profile into another repository.

```bash
agentic-discipline bootstrap --target ../my-project --stack python
```
