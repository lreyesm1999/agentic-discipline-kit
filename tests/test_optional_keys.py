"""Inputs that leave out an optional key are read as empty, not refused or crashed.

Profiles, quality configurations and requirement graphs come from files a person
writes. Where a key may be missing, the reader substitutes an empty value and goes
on; each case omits one such key and pins what is produced instead.
"""

from __future__ import annotations

import json
from pathlib import Path

from agentic_discipline.profiles import (
    Detection,
    Profile,
    annotate_gate_availability,
    build_quality_config,
)
from agentic_discipline.quality import extract_metrics
from agentic_discipline.requirements import validate_requirement_graph
from agentic_discipline.validation import validate_quality_config


def test_a_profile_without_gates_contributes_none(tmp_path: Path) -> None:
    config = tmp_path / "quality.json"
    config.write_text(json.dumps({"project": "x"}), encoding="utf-8")
    profile = Profile(id="bare", label="Bare", config_path=config, detectors=())
    detection = Detection(profile="bare", label="Bare", root=tmp_path, confidence=1.0, evidence=())

    built = build_quality_config(tmp_path, [detection], {"bare": profile})

    assert built["gates"] == []


def test_a_configuration_without_gates_is_returned_unchanged(tmp_path: Path) -> None:
    assert annotate_gate_availability(tmp_path, {"project": "x"}) == {"project": "x"}


def test_a_json_parser_without_metrics_extracts_nothing() -> None:
    assert extract_metrics(json.dumps({"coverage": 90}), {"type": "json"}) == {}


def test_a_regex_parser_without_metrics_is_reported_not_crashed() -> None:
    config = {
        "project": "x",
        "gates": [{"name": "t", "command": ["true"], "parser": {"type": "regex"}}],
    }

    errors = validate_quality_config(config)

    assert errors and all("gates.0" in error for error in errors)


def test_a_graph_without_nodes_still_reports_its_edges() -> None:
    graph = {"feature_id": "f", "edges": [{"from": "A", "to": "B", "relation": "verified_by"}]}

    errors = validate_requirement_graph(graph)

    assert "edges.0.from: unknown node 'A'" in errors
    assert "edges.0.to: unknown node 'B'" in errors
