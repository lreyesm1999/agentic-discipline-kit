import json
from pathlib import Path

import pytest

from agentic_discipline.validation import (
    ValidationError,
    load_json,
    load_quality_config,
    validate_quality_config,
)


def test_load_json_reports_missing_invalid_and_non_object(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="not found"):
        load_json(tmp_path / "missing.json")
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    with pytest.raises(ValidationError, match="line 1"):
        load_json(invalid)
    array = tmp_path / "array.json"
    array.write_text("[]", encoding="utf-8")
    with pytest.raises(ValidationError, match="JSON object"):
        load_json(array)


def test_quality_config_rejects_duplicate_and_undeclared_metrics(tmp_path: Path) -> None:
    config = {
        "project": "demo",
        "gates": [
            {"name": "same", "command": "python -V"},
            {
                "name": "same",
                "command": "python -V",
                "parser": {"type": "regex", "metrics": {"lines": "(1)"}},
                "thresholds": {"branches": {"min": 80}},
            },
        ],
    }
    errors = validate_quality_config(config)
    assert any("duplicate gate" in error for error in errors)
    assert any("not declared" in error for error in errors)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValidationError, match="invalid quality configuration"):
        load_quality_config(path)


def test_quality_config_rejects_unknown_properties() -> None:
    errors = validate_quality_config(
        {
            "project": "demo",
            "gates": [{"name": "test", "command": "python -V", "magic": True}],
        }
    )
    assert any("Additional properties" in error for error in errors)


def test_quality_config_rejects_invalid_regex() -> None:
    errors = validate_quality_config(
        {
            "project": "demo",
            "gates": [
                {
                    "name": "coverage",
                    "command": ["coverage", "report"],
                    "parser": {"type": "regex", "metrics": {"lines": "("}},
                }
            ],
        }
    )
    assert any("invalid regex" in error for error in errors)
