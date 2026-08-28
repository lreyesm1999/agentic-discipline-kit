import json

import pytest

from agentic_discipline.risk import assess_risk, level_at_least, load_risk_weights


def test_trivial_change_is_low_risk() -> None:
    result = assess_risk("+ typo fix", ["README.md"])
    assert result.level == "LOW"


def test_money_and_auth_change_escalates() -> None:
    result = assess_risk(
        "+ update payment balance authorization token",
        ["src/payment.py", "src/auth.py"],
    )
    assert result.level in {"HIGH", "CRITICAL"}
    assert result.factors["money"]
    assert result.factors["auth"]


def test_risk_levels_cover_standard_and_critical() -> None:
    standard = assess_risk("+ route endpoint", ["src/api.py"])
    assert standard.level == "STANDARD"

    critical = assess_risk(
        "+ auth payment migration security delete crypto transaction",
        [f"src/{i}.py" for i in range(10)],
    )
    assert critical.level == "CRITICAL"


def test_removed_sensitive_text_does_not_raise_risk() -> None:
    result = assess_risk("- remove payment password migration", ["docs/notes.md"])
    assert result.level == "LOW"


def test_risk_level_threshold_order() -> None:
    assert level_at_least("HIGH", "STANDARD")
    assert not level_at_least("LOW", "HIGH")


def test_risk_weights_are_validated(tmp_path) -> None:
    path = tmp_path / "weights.json"
    weights = {
        "auth": 1,
        "money": 1,
        "migration": 1,
        "public_api": 1,
        "concurrency": 1,
        "security": 1,
        "architecture": 1,
        "infra": 1,
        "destructive": 1,
        "crypto": 1,
    }
    path.write_text(json.dumps(weights), encoding="utf-8")
    assert load_risk_weights(path) == weights
    weights["auth"] = -1
    path.write_text(json.dumps(weights), encoding="utf-8")
    with pytest.raises(ValueError, match="non-negative"):
        load_risk_weights(path)
