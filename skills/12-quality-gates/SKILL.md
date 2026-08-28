# 12 — Metric-Aware Quality Gates

## Purpose
Run deterministic tools and evaluate structured metrics against policy.

## Trigger
Implementation is functionally green.

## Inputs
- agentic.config.json
- repo state

## Outputs
- artifacts/quality-report.json
- artifacts/quality-report.md

## Procedure
1. Run scripts/quality_engine.py.
2. Execute configured commands.
3. Parse structured metrics when parsers exist.
4. Evaluate thresholds.
5. Treat parser/tool failures as BLOCKED/FAIL, never PASS.
6. Fix root causes and rerun.

## Evidence required
- commands
- exit codes
- parsed metrics

## Forbidden
- fabricated metrics
- shell-only PASS when threshold parsing is required

## Stop conditions
- required tool unavailable

## Definition of done
- every required gate passes
