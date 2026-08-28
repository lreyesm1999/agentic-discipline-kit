from agentic_discipline.requirements import orphan_requirements, validate_requirement_graph


def test_orphan_requirement_is_detected() -> None:
    graph = {
        "nodes": [
            {"id": "FR-001", "type": "requirement"},
            {"id": "SPEC-001", "type": "spec"},
        ],
        "edges": [],
    }
    assert orphan_requirements(graph) == ["FR-001"]


def test_traced_requirement_is_not_orphaned() -> None:
    graph = {
        "nodes": [
            {"id": "FR-001", "type": "requirement"},
            {"id": "SPEC-001", "type": "spec"},
        ],
        "edges": [
            {"from": "FR-001", "to": "SPEC-001", "relation": "specified_by"},
        ],
    }
    assert orphan_requirements(graph) == []


def test_invalid_edge_does_not_satisfy_traceability() -> None:
    graph = {
        "feature_id": "FEAT-001",
        "nodes": [{"id": "FR-001", "type": "requirement"}],
        "edges": [{"from": "FR-001", "to": "MISSING", "relation": "verified_by"}],
    }
    assert orphan_requirements(graph) == ["FR-001"]
    assert any("unknown node" in error for error in validate_requirement_graph(graph))


def test_complete_graph_requires_path_to_evidence() -> None:
    graph = {
        "feature_id": "FEAT-001",
        "nodes": [
            {"id": "FR-001", "type": "requirement"},
            {"id": "AC-001", "type": "acceptance"},
            {"id": "EV-001", "type": "evidence"},
        ],
        "edges": [
            {"from": "FR-001", "to": "AC-001", "relation": "verified_by"},
            {"from": "AC-001", "to": "EV-001", "relation": "evidenced_by"},
        ],
    }
    assert validate_requirement_graph(graph, complete=True) == []
    graph["edges"].pop()
    assert any(
        "reaches evidence" in error for error in validate_requirement_graph(graph, complete=True)
    )


def test_graph_rejects_duplicates_bad_types_self_edges_and_missing_paths(
    tmp_path,
) -> None:
    graph = {
        "feature_id": "FEAT-001",
        "nodes": [
            {"id": "FR-001", "type": "requirement", "path": "missing.md"},
            {"id": "FR-001", "type": "code"},
            {"id": "CODE-001", "type": "code"},
        ],
        "edges": [
            {"from": "FR-001", "to": "FR-001", "relation": "depends_on"},
            {"from": "FR-001", "to": "CODE-001", "relation": "specified_by"},
        ],
    }
    errors = validate_requirement_graph(graph, base_path=tmp_path)
    assert any("duplicate node" in error for error in errors)
    assert any("file not found" in error for error in errors)
    assert any("self-reference" in error for error in errors)
    assert any("cannot connect" in error for error in errors)


def test_graph_handles_malformed_collection_members() -> None:
    graph = {
        "feature_id": "FEAT-001",
        "nodes": ["bad", {"id": "FR-001", "type": "requirement"}],
        "edges": ["bad"],
    }
    errors = validate_requirement_graph(graph)
    assert errors
    assert orphan_requirements(graph) == ["FR-001"]
    assert validate_requirement_graph({"feature_id": "x", "nodes": {}, "edges": {}})
