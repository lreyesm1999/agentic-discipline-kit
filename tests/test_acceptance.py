import pytest

from agentic_discipline.acceptance import (
    AcceptanceError,
    parse_feature_text,
    validate_acceptance_ir,
)

FEATURE = """
Feature: Checkout

  # REQ: FR-001 SEC-001
  @AC-001
  Scenario: successful checkout
    Given a valid cart
    When the user pays
    Then the order is created
"""


def test_compile_acceptance_ir() -> None:
    result = parse_feature_text(FEATURE, "checkout")
    assert result["feature_id"] == "checkout"
    assert len(result["scenarios"]) == 1
    scenario = result["scenarios"][0]
    assert scenario["id"] == "AC-001"
    assert scenario["requirements"] == ["FR-001", "SEC-001"]
    assert [step["kind"] for step in scenario["steps"]] == ["given", "when", "then"]


def test_compile_feature_writes_output(tmp_path) -> None:
    from agentic_discipline.acceptance import compile_feature

    source = tmp_path / "auto.feature"
    output = tmp_path / "auto.json"
    source.write_text(
        "# REQ: FR-009\nScenario: automatic id\nGiven x\nWhen y\nThen z\n",
        encoding="utf-8",
    )
    result = compile_feature(source, output)
    assert result["scenarios"][0]["id"] == "AC-001"
    assert output.exists()


def test_acceptance_rejects_incomplete_and_unsupported_scenarios() -> None:
    with pytest.raises(AcceptanceError, match="at least one requirement"):
        parse_feature_text("Scenario: missing contract\nGiven x\nWhen y\nThen z")
    with pytest.raises(AcceptanceError, match="unsupported Gherkin"):
        parse_feature_text(
            "# REQ: FR-001\nScenario Outline: demo\nGiven x\nWhen y\nThen z\nExamples:\n"
        )


def test_acceptance_ir_reports_duplicates_and_missing_steps() -> None:
    scenario = {
        "id": "AC-001",
        "requirements": ["FR-001"],
        "name": "demo",
        "tags": [],
        "steps": [{"kind": "given", "text": "x"}],
    }
    errors = validate_acceptance_ir(
        {"feature_id": "demo", "scenarios": [scenario, scenario.copy(), "invalid"]}
    )
    assert any("duplicate scenario" in error for error in errors)
    assert any("missing when" in error for error in errors)
    assert any("missing then" in error for error in errors)
