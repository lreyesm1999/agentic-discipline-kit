"""Feature parsing, threshold checks, orphan detection and adapter names, case by case.

Mutation testing found these decisions unpinned: lower-case Gherkin keywords, what
happens after the first unknown or invalid metric, a value exactly at its maximum,
edges whose fields are not text, and the message naming unknown adapters. Each case
states the exact outcome.
"""

from __future__ import annotations

from typing import Any

import pytest

from agentic_discipline.acceptance import AcceptanceError, parse_feature_text
from agentic_discipline.adapters import ALIASES, EMITTERS, resolve_adapters
from agentic_discipline.quality import evaluate_thresholds
from agentic_discipline.requirements import orphan_requirements

# --- acceptance -----------------------------------------------------------------------------

FEATURE = (
    "# REQ: FR-1\n"
    "Feature: Orders\n"
    "  Scenario: pays\n"
    "    Given a cart\n"
    "    When it is paid\n"
    "    Then an order exists\n"
)


def test_scenario_keywords_are_recognised_in_any_letter_case() -> None:
    result = parse_feature_text(FEATURE.replace("Scenario:", "scenario:"))

    assert [s["name"] for s in result["scenarios"]] == ["pays"]


def test_unsupported_keywords_are_refused_in_any_letter_case() -> None:
    with pytest.raises(AcceptanceError) as caught:
        parse_feature_text(FEATURE + "  background: shared\n")

    assert str(caught.value) == (
        "invalid acceptance feature: unsupported Gherkin syntax: background: shared"
    )


# --- thresholds -----------------------------------------------------------------------------


def test_every_metric_is_checked_after_an_unknown_or_invalid_one() -> None:
    metrics: dict[str, float | str] = {"invalid": "n/a", "lines": 70}
    thresholds = {"missing": {"min": 1}, "invalid": {"min": 1}, "lines": {"min": 80}}

    assert evaluate_thresholds(metrics, thresholds) == [
        "missing=UNKNOWN",
        "invalid=INVALID",
        "lines 70.0 < 80",
    ]


def test_a_value_at_its_maximum_passes_and_an_exact_rule_names_both_values() -> None:
    assert evaluate_thresholds({"size": 10}, {"size": {"max": 10}}) == []
    assert evaluate_thresholds({"size": 11}, {"size": {"eq": 10}}) == ["size 11.0 != 10"]


# --- orphan requirements --------------------------------------------------------------------


NODES = [{"id": "FR-1", "type": "requirement"}, {"id": "AC-1", "type": "acceptance"}]


def test_a_well_formed_edge_links_the_requirement() -> None:
    edge = {"from": "FR-1", "to": "AC-1", "relation": "verified_by"}
    assert orphan_requirements({"nodes": NODES, "edges": [edge]}) == []


@pytest.mark.parametrize(
    "edge",
    [
        {"from": ["FR-1"], "to": "AC-1", "relation": "verified_by"},
        {"from": "FR-1", "to": ["AC-1"], "relation": "verified_by"},
        {"from": "FR-1", "to": "AC-1", "relation": ["verified_by"]},
    ],
    ids=["list-source", "list-target", "list-relation"],
)
def test_edges_whose_fields_are_not_text_are_ignored(edge: dict[str, Any]) -> None:
    assert orphan_requirements({"nodes": NODES, "edges": [edge]}) == ["FR-1"]


# --- adapters -------------------------------------------------------------------------------


def test_unknown_adapters_are_named_with_every_available_one() -> None:
    available = ", ".join(sorted(set(EMITTERS) | set(ALIASES)))

    with pytest.raises(ValueError) as caught:
        resolve_adapters(["zeta", "claude", "alpha"])

    assert str(caught.value) == f"unknown adapters: alpha, zeta; available: {available}"
