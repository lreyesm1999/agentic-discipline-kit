from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentic_discipline.quality import (
    evaluate_thresholds,
    extract_metrics,
    run_gate,
    run_quality,
)
from agentic_discipline.validation import ValidationError


def test_json_metric_parser() -> None:
    parser = {
        "type": "json",
        "metrics": {
            "coverage": "summary.lines",
            "first": "items.0.value",
            "missing": "does.not.exist",
        },
    }
    metrics = extract_metrics(
        json.dumps({"summary": {"lines": 95}, "items": [{"value": 7}]}),
        parser,
    )
    assert metrics == {"coverage": 95, "first": 7}


def test_json_metric_parser_invalid_and_unknown_type() -> None:
    assert extract_metrics("not-json", {"type": "json", "metrics": {"x": "x"}}) == {}
    assert extract_metrics("anything", {"type": "unknown"}) == {}
    assert extract_metrics("anything", None) == {}


def test_threshold_min_max_eq_and_pass() -> None:
    failures = evaluate_thresholds(
        {"low": 1.0, "high": 9.0, "eq": 2.0},
        {
            "low": {"min": 2.0},
            "high": {"max": 8.0},
            "eq": {"eq": 3.0},
        },
    )
    assert len(failures) == 3
    assert evaluate_thresholds({"x": 5.0}, {"x": {"min": 4.0, "max": 6.0}}) == []
    assert evaluate_thresholds({"x": "not-a-number"}, {"x": {"min": 4.0}}) == ["x=INVALID"]


def test_run_gate_pass_and_threshold_fail(tmp_path: Path) -> None:
    gate = {
        "name": "coverage",
        "command": "python -c \"print('Lines: 95%')\"",
        "required": True,
        "parser": {"type": "regex", "metrics": {"lines": r"Lines:\s*([0-9.]+)%"}},
        "thresholds": {"lines": {"min": 90}},
    }
    result = run_gate(gate, cwd=tmp_path)
    assert result.status == "PASS"
    assert result.metrics["lines"] == 95.0

    gate["thresholds"] = {"lines": {"min": 99}}
    result = run_gate(gate, cwd=tmp_path)
    assert result.status == "FAIL"
    assert result.threshold_failures


def test_run_quality_pass_and_fail(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "project": "demo",
                "gates": [
                    {
                        "name": "ok",
                        "command": "python -c \"print('ok')\"",
                        "required": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert run_quality(config, cwd=tmp_path)["status"] == "PASS"

    config.write_text(
        json.dumps(
            {
                "project": "demo",
                "gates": [
                    {
                        "name": "bad",
                        "command": 'python -c "raise SystemExit(3)"',
                        "required": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    report = run_quality(config, cwd=tmp_path)
    assert report["status"] == "FAIL"
    assert report["results"][0]["exit_code"] == 3


def test_run_quality_uses_gate_working_directory(tmp_path: Path) -> None:
    component = tmp_path / "component"
    component.mkdir()
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "project": "monorepo",
                "gates": [
                    {
                        "name": "cwd",
                        "command": [
                            "python",
                            "-c",
                            "import pathlib; raise SystemExit(0 if pathlib.Path('marker').exists() else 1)",
                        ],
                        "working_directory": "component",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (component / "marker").write_text("", encoding="utf-8")

    assert run_quality(config)["status"] == "PASS"


def test_run_quality_rejects_empty_or_optional_only_gates(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"project": "demo", "gates": []}), encoding="utf-8")
    with pytest.raises(ValidationError, match=r"minItems|non-empty|\[\]"):
        run_quality(config, cwd=tmp_path)

    config.write_text(
        json.dumps(
            {
                "project": "demo",
                "gates": [{"name": "optional", "command": "python -V", "required": False}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="at least one gate must be required"):
        run_quality(config, cwd=tmp_path)


def test_run_gate_timeout_is_error(tmp_path: Path) -> None:
    gate = {
        "name": "slow",
        "command": 'python -c "import time; time.sleep(2)"',
        "required": True,
        "timeout_seconds": 0.05,
    }
    result = run_gate(gate, cwd=tmp_path)
    assert result.status == "ERROR"
    assert result.exit_code == 124


def test_run_gate_missing_executable_is_error(tmp_path: Path) -> None:
    result = run_gate(
        {"name": "missing", "command": ["definitely-not-an-adk-command"], "required": True},
        cwd=tmp_path,
    )
    assert result.status == "ERROR"
    assert result.exit_code == 127
