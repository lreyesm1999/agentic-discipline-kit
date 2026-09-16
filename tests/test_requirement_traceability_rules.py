"""Traceability rules asserted by exact outcome rather than by the mere presence of errors."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from agentic_discipline.requirements import orphan_requirements, validate_requirement_graph


def test_only_requirement_nodes_need_a_path_to_evidence() -> None:
    graph = {
        "feature_id": "FEAT-001",
        "nodes": [
            {"id": "FR-001", "type": "requirement"},
            {"id": "SPEC-001", "type": "spec"},
            {"id": "EV-001", "type": "evidence"},
        ],
        "edges": [{"from": "FR-001", "to": "EV-001", "relation": "evidenced_by"}],
    }
    assert validate_requirement_graph(graph, complete=True) == []


def test_every_untraced_requirement_is_named_even_after_other_node_types() -> None:
    graph = {
        "feature_id": "FEAT-001",
        "nodes": [
            {"id": "EV-001", "type": "evidence"},
            {"id": "FR-001", "type": "requirement"},
            {"id": "FR-002", "type": "requirement"},
        ],
        "edges": [{"from": "FR-001", "to": "EV-001", "relation": "evidenced_by"}],
    }
    assert validate_requirement_graph(graph, complete=True) == [
        "requirements.FR-002: no traceability path reaches evidence"
    ]


def test_cycle_without_evidence_terminates_and_is_reported() -> None:
    graph = {
        "feature_id": "FEAT-001",
        "nodes": [
            {"id": "FR-001", "type": "requirement"},
            {"id": "AC-001", "type": "acceptance"},
            {"id": "AC-002", "type": "acceptance"},
        ],
        "edges": [
            {"from": "FR-001", "to": "AC-001", "relation": "verified_by"},
            {"from": "AC-001", "to": "AC-002", "relation": "verified_by"},
            {"from": "AC-002", "to": "AC-001", "relation": "verified_by"},
        ],
    }
    outcome: list[list[str]] = []
    # Run in a thread so a traversal that never marks nodes visited fails the
    # test promptly instead of hanging the suite.
    worker = threading.Thread(
        target=lambda: outcome.append(validate_requirement_graph(graph, complete=True)),
        daemon=True,
    )
    worker.start()
    worker.join(timeout=5)
    assert outcome == [["requirements.FR-001: no traceability path reaches evidence"]]


def test_malformed_members_do_not_stop_validation_of_later_members(tmp_path: Path) -> None:
    graph: dict[str, Any] = {
        "feature_id": "FEAT-001",
        "nodes": ["bad", {"id": "FR-001", "type": "requirement", "path": "missing.md"}],
        "edges": ["bad", {"from": "FR-001", "to": "FR-001", "relation": "depends_on"}],
    }
    errors = validate_requirement_graph(graph, base_path=tmp_path)
    assert "nodes.1.path: file not found: missing.md" in errors
    assert "edges.1: self-reference is not allowed" in errors


def test_rejected_nodes_and_edges_do_not_stop_later_ones_from_tracing() -> None:
    graph = {
        "feature_id": "FEAT-001",
        "nodes": [
            {"id": "FR-001", "type": "requirement"},
            {"id": "FR-001", "type": "code"},
            {"id": "CODE-001", "type": "code"},
            {"id": "EV-001", "type": "evidence"},
        ],
        "edges": [
            {"from": "GHOST", "to": "EV-001", "relation": "evidenced_by"},
            {"from": "FR-001", "to": "CODE-001", "relation": "specified_by"},
            {"from": "FR-001", "to": "CODE-001", "relation": "implemented_by"},
            {"from": "CODE-001", "to": "EV-001", "relation": "evidenced_by"},
        ],
    }
    assert validate_requirement_graph(graph, complete=True) == [
        "nodes.1.id: duplicate node id 'FR-001'",
        "edges.0.from: unknown node 'GHOST'",
        "edges.1: specified_by cannot connect requirement to code",
    ]


def test_edge_with_wrong_endpoint_types_does_not_trace_a_requirement() -> None:
    graph = {
        "nodes": [{"id": "FR-001", "type": "requirement"}, {"id": "CODE-001", "type": "code"}],
        "edges": [{"from": "FR-001", "to": "CODE-001", "relation": "specified_by"}],
    }
    assert orphan_requirements(graph) == ["FR-001"]


def test_orphan_detection_skips_malformed_edges_and_keeps_scanning() -> None:
    graph = {
        "nodes": [{"id": "FR-001", "type": "requirement"}, {"id": "SPEC-001", "type": "spec"}],
        "edges": [
            "bad",
            {"from": "FR-001", "to": "GHOST", "relation": "specified_by"},
            {"from": "FR-001", "to": "SPEC-001", "relation": "specified_by"},
        ],
    }
    assert orphan_requirements(graph) == []


def test_graph_without_collections_has_no_orphans() -> None:
    assert orphan_requirements({}) == []
