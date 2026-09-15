"""Acceptance feature parsing, scenario by scenario.

`parse_feature_text` turns Gherkin into the acceptance IR that requirement graphs and
verifiers reference by id. The existing test parsed one scenario, so requirement
carry-over, tag handling, generated ids or the refusal of unsupported syntax could
drift unnoticed. Each case compares the whole IR or the whole error.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline.acceptance import (
    AcceptanceError,
    compile_feature,
    parse_feature_text,
    validate_acceptance_ir,
)
from agentic_discipline.common import AgenticError

FEATURE = """\
Feature: Checkout
  Given a step before any scenario is ignored

  # REQ: FR-001, FR-002  FR-003
  @ac-7 @smoke not-a-tag
  Scenario:   Pay with a saved card
    GIVEN a saved card
    When the customer pays
    Then the order is paid
    And a receipt is sent

  # req: FR-009
  Scenario: Pay with a new card
    Given a new card
    when the customer pays
    then the order is paid

  @AC-12
  Scenario: Retry a declined card
    Given a declined card
    When the customer retries
    Then the order is paid
"""


def _raises(text: str) -> str:
    with pytest.raises(AcceptanceError) as caught:
        parse_feature_text(text, "demo")
    return str(caught.value)


def test_feature_becomes_ordered_scenarios_with_requirements_tags_and_steps() -> None:
    assert parse_feature_text(FEATURE, "checkout") == {
        "feature_id": "checkout",
        "scenarios": [
            {
                "id": "AC-7",
                "requirements": ["FR-001", "FR-002", "FR-003"],
                "name": "Pay with a saved card",
                "tags": ["ac-7", "smoke"],
                "steps": [
                    {"kind": "given", "text": "a saved card"},
                    {"kind": "when", "text": "the customer pays"},
                    {"kind": "then", "text": "the order is paid"},
                    {"kind": "and", "text": "a receipt is sent"},
                ],
            },
            {
                "id": "AC-002",
                "requirements": ["FR-009"],
                "name": "Pay with a new card",
                "tags": [],
                "steps": [
                    {"kind": "given", "text": "a new card"},
                    {"kind": "when", "text": "the customer pays"},
                    {"kind": "then", "text": "the order is paid"},
                ],
            },
            {
                "id": "AC-12",
                "requirements": ["FR-009"],
                "name": "Retry a declined card",
                "tags": ["AC-12"],
                "steps": [
                    {"kind": "given", "text": "a declined card"},
                    {"kind": "when", "text": "the customer retries"},
                    {"kind": "then", "text": "the order is paid"},
                ],
            },
        ],
    }


def test_feature_id_defaults_to_feature() -> None:
    text = "# REQ: FR-1\nScenario: s\nGiven a\nWhen b\nThen c\n"
    assert parse_feature_text(text)["feature_id"] == "feature"


def _invalid(scenarios: list[dict[str, Any]], *extra: str) -> str:
    errors = validate_acceptance_ir({"feature_id": "demo", "scenarios": scenarios})
    return "invalid acceptance feature: " + "; ".join([*errors, *extra])


def test_structural_problems_are_reported_together() -> None:
    text = "Scenario: one\nGiven a\nThen c\n@AC-001\nScenario: two\nGiven a\nWhen b\nThen c\n"
    scenarios = [
        {
            "id": "AC-001",
            "requirements": [],
            "name": "one",
            "tags": [],
            "steps": [{"kind": "given", "text": "a"}, {"kind": "then", "text": "c"}],
        },
        {
            "id": "AC-001",
            "requirements": [],
            "name": "two",
            "tags": ["AC-001"],
            "steps": [
                {"kind": "given", "text": "a"},
                {"kind": "when", "text": "b"},
                {"kind": "then", "text": "c"},
            ],
        },
    ]
    message = _raises(text)
    assert message == _invalid(scenarios)
    for part in (
        "scenarios.0.requirements: at least one requirement is required",
        "scenarios.0.steps: missing when step",
        "scenarios.1.id: duplicate scenario id 'AC-001'",
    ):
        assert part in message


def test_an_empty_feature_has_no_scenarios() -> None:
    message = _raises("Feature: nothing\n")
    assert message == _invalid([])
    empty = validate_acceptance_ir({"feature_id": "demo", "scenarios": []})
    assert empty[-1] == "scenarios: at least one scenario is required"


def test_unsupported_gherkin_is_refused_by_line() -> None:
    text = (
        "# REQ: FR-1\n"
        "Background:\n"
        "Scenario Outline: many\n"
        "Scenario: one\n"
        "Given a\n"
        "When b\n"
        "Then c\n"
        "But not d\n"
        "Examples:\n"
        "Rule: grouped\n"
    )
    scenarios = [
        {
            "id": "AC-001",
            "requirements": ["FR-1"],
            "name": "one",
            "tags": [],
            "steps": [
                {"kind": "given", "text": "a"},
                {"kind": "when", "text": "b"},
                {"kind": "then", "text": "c"},
            ],
        },
    ]
    assert _raises(text) == _invalid(
        scenarios,
        "unsupported Gherkin syntax: Background:, Scenario Outline: many, But not d, "
        "Examples:, Rule: grouped",
    )


def test_validation_skips_malformed_entries_without_crashing() -> None:
    errors = validate_acceptance_ir(
        {"feature_id": "x", "scenarios": ["bad", {"id": 3, "steps": ["x"]}]}
    )
    assert "scenarios.1.requirements: at least one requirement is required" in errors
    assert "scenarios.1.steps: missing given step" in errors
    assert not any("duplicate" in error for error in errors)


def test_acceptance_errors_are_agentic_errors() -> None:
    assert issubclass(AcceptanceError, AgenticError)


def test_compile_feature_writes_indented_ir_named_after_the_file(tmp_path: Path) -> None:
    source = tmp_path / "checkout.feature"
    source.write_text(FEATURE, encoding="utf-8")
    output = tmp_path / "out" / "nested" / "checkout.json"

    result = compile_feature(source, output)

    assert result == parse_feature_text(FEATURE, "checkout")
    assert output.read_text(encoding="utf-8") == json.dumps(result, indent=2)
