# CLI Reference

The installed command is:

```bash
agentic-discipline
```

## init

Initializes the current project without requiring a stack selection:

```bash
agentic-discipline init
```

It detects known manifests up to four directories deep, composes all detected profiles, installs the
engineering contracts, and writes `agentic.config.json`. Existing files are preserved unless `--force`
is supplied.

Detection can be overridden or extended:

```bash
agentic-discipline init --profile typescript --profile dotnet
agentic-discipline init --profile-file ./rust-profile.json --profile rust
agentic-discipline init --max-depth 6
```

When nothing is recognized, `init` emits a generic Git-based gate instead of rejecting the project.
See [Project profiles](profiles.md) for the descriptor format.

The generated configuration is intentionally conservative: it recommends gates but does not install
or execute project dependencies during initialization.

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

Legacy alias for `init`. `--stack` is now an optional profile override; omitting it enables detection.

```bash
agentic-discipline bootstrap --target ../my-project
```

## verify and verifier

`init` installs the v3 `.agentic/` payload. A verifier package contains `verifier.json` and its
executable entrypoint. The metadata declares the claim, requirement IDs, command, timeout, expected
exit code, dependencies, and sensitivity state.

```bash
agentic-discipline verifier register checks/payment-check
agentic-discipline verifier list
agentic-discipline verifier inspect VER-017
agentic-discipline verifier validate VER-017
agentic-discipline verify VER-017
agentic-discipline verifier protect VER-017
```

Generated verifiers start as `DRAFT`. They must include sensitivity evidence before they can be
protected. Missing commands or environment variables produce `BLOCKED`; an executed failing
condition produces `FAIL`.

## adapters

Synchronize thin vendor projections from the canonical `.agentic` source. Existing user content outside
the managed block is preserved and repeated runs are idempotent.

```bash
agentic-discipline adapters sync
agentic-discipline adapters sync --adapter claude --adapter cursor
```

## migrate

Migrate an existing v2.1 installation without deleting contracts or evidence:

```bash
agentic-discipline migrate --to 3.0
```

The command writes `artifacts/migration-v3-report.json`.

## hygiene

Check evolution lifecycle metadata, unresolved removals, temporary artifacts, and suspicious fallback
additions:

```bash
agentic-discipline hygiene
agentic-discipline hygiene --base-ref origin/main
```
