"""Change risk scoring, factor by factor and threshold by threshold.

The risk score decides review depth and can fail CI through `--fail-at`. Existing tests
checked a few representative diffs, so a level boundary, the file-count cap, the rule
that only added lines count, or weight validation could shift unnoticed. Each case
pins the exact assessment.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agentic_discipline.risk import (
    PATTERNS,
    WEIGHTS,
    RiskAssessment,
    assess_risk,
    assess_risk_with_weights,
    level_at_least,
    load_risk_weights,
)

NO_FACTORS = dict.fromkeys(PATTERNS, False)


def _only(name: str, weight: int) -> dict[str, int]:
    return {**dict.fromkeys(PATTERNS, 0), name: weight}


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("auth", "Refresh the OAuth session"),
        ("money", "wallet"),
        ("migration", "alembic"),
        ("public_api", "src/api/orders.py"),
        ("concurrency", "Mutex"),
        ("security", "sanitize"),
        ("architecture", "core/rules.py"),
        ("infra", ".github/workflows/ci.yml"),
        ("destructive", "TRUNCATE"),
        ("crypto", "aes"),
    ],
)
def test_each_factor_adds_its_weight_once(name: str, text: str) -> None:
    diff = f"+{text}\n+{text} again\n"
    assert assess_risk_with_weights(diff, [], _only(name, 7)) == RiskAssessment(
        score=7, level="LOW", files_changed=0, factors={**NO_FACTORS, name: True}
    )


@pytest.mark.parametrize(
    ("weight", "level"),
    [(14, "LOW"), (15, "STANDARD"), (39, "STANDARD"), (40, "HIGH"), (74, "HIGH"), (75, "CRITICAL")],
)
def test_level_boundaries(weight: int, level: str) -> None:
    result = assess_risk_with_weights("+payment", [], _only("money", weight))
    assert (result.score, result.level) == (weight, level)


def test_files_add_two_points_each_up_to_twenty() -> None:
    three = assess_risk_with_weights("", ["a.py", "b.py", "c.py"], WEIGHTS)
    assert three == RiskAssessment(score=6, level="LOW", files_changed=3, factors=NO_FACTORS)
    many = [f"file{i}.txt" for i in range(11)]
    assert assess_risk_with_weights("", many, WEIGHTS) == RiskAssessment(
        score=20, level="STANDARD", files_changed=11, factors=NO_FACTORS
    )


def test_file_names_count_as_evidence_and_the_score_is_capped_at_100() -> None:
    result = assess_risk_with_weights("", ["billing/delete_wallet.py"], {**WEIGHTS, "money": 90})
    assert result == RiskAssessment(
        score=100,
        level="CRITICAL",
        files_changed=1,
        factors={**NO_FACTORS, "money": True, "destructive": True},
    )


def test_only_added_lines_count_not_removed_lines_or_file_headers() -> None:
    diff = "+++ b/payment.py\n--- a/payment.py\n-drop table\n context delete\n+value = 1\n"
    assert assess_risk_with_weights(diff, [], WEIGHTS) == RiskAssessment(
        score=0, level="LOW", files_changed=0, factors=NO_FACTORS
    )


def test_default_weights_are_used_by_assess_risk() -> None:
    assert assess_risk("+invoice", iter(["src/pay.py"])) == RiskAssessment(
        score=32, level="STANDARD", files_changed=1, factors={**NO_FACTORS, "money": True}
    )


def _weights_file(tmp_path: Path, **changes: object) -> Path:
    import json

    path = tmp_path / "risk-weights.json"
    path.write_text(json.dumps({**WEIGHTS, "extra": 99, **changes}), encoding="utf-8")
    return path


def test_weights_file_is_read_in_pattern_order_ignoring_extras(tmp_path: Path) -> None:
    weights = load_risk_weights(_weights_file(tmp_path, money=0))
    assert list(weights) == list(PATTERNS)
    assert weights == {**WEIGHTS, "money": 0}


@pytest.mark.parametrize("value", [-1, 1.5, "30", None])
def test_every_weight_must_be_a_non_negative_integer(tmp_path: Path, value: object) -> None:
    with pytest.raises(ValueError) as caught:
        load_risk_weights(_weights_file(tmp_path, money=value))
    assert str(caught.value) == "risk weight 'money' must be a non-negative integer"


def test_a_missing_weight_is_named(tmp_path: Path) -> None:
    import json

    path = tmp_path / "risk-weights.json"
    path.write_text(
        json.dumps({k: v for k, v in WEIGHTS.items() if k != "crypto"}), encoding="utf-8"
    )
    with pytest.raises(ValueError) as caught:
        load_risk_weights(path)
    assert str(caught.value) == "risk weight 'crypto' must be a non-negative integer"


@pytest.mark.parametrize(
    ("level", "threshold", "expected"),
    [
        ("LOW", "LOW", True),
        ("LOW", "STANDARD", False),
        ("STANDARD", "LOW", True),
        ("STANDARD", "HIGH", False),
        ("HIGH", "STANDARD", True),
        ("HIGH", "CRITICAL", False),
        ("CRITICAL", "HIGH", True),
        ("CRITICAL", "CRITICAL", True),
    ],
)
def test_level_ordering(level: str, threshold: str, expected: bool) -> None:
    assert level_at_least(level, threshold) is expected


def test_file_names_and_added_lines_are_matched_separately() -> None:
    # "mute" plus any separator text must not read as "mutex".
    assert assess_risk_with_weights("+ok", ["mute"], WEIGHTS).factors == NO_FACTORS


def test_a_missing_weights_file_is_named(tmp_path: Path) -> None:
    from agentic_discipline.validation import ValidationError

    missing = tmp_path / "absent.json"
    with pytest.raises(ValidationError) as caught:
        load_risk_weights(missing)
    assert str(caught.value) == f"risk weights not found: {missing}"
