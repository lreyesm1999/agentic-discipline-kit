# Migration Guide — v1 → v2

## Keep

Your existing:
- specs
- acceptance
- architecture
- policies
- project tests
- existing tool configs

## Replace

Replace:
- root `AGENTS.md`
- root `MASTER_PROMPT.md`
- `skills/`
- generic `quality_gate.py`

with v2 equivalents.

## New mandatory concepts

### Requirement graph
Create:

```text
artifacts/requirements/<feature-id>.graph.json
```

Use `schemas/requirement-graph.schema.json`.

### Acceptance IR
Compile acceptance contracts to:

```text
artifacts/acceptance/<feature-id>.ir.json
```

### Risk classification
Run before selecting gate depth:

```bash
python scripts/risk_score.py --base-ref HEAD~1 --json
```

### Integrity audit
Run before release:

```bash
python scripts/integrity_audit.py --base-ref HEAD~1
```

### Evidence ledger
Persist release evidence:

```bash
python scripts/evidence_ledger.py append --artifact artifacts/quality-report.json
```

### Retrospective
Record recurring process failures in:

```text
.agent-memory/failures.jsonl
```

Do not treat agent-memory as business truth.
