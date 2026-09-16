"""Legacy requirement graph import, record by record.

The import turns a v1 requirement graph into historical v2 knowledge. Existing tests
only checked that a dry run reports itself and that one node became HISTORICAL, so a
node could land in the wrong graph, an edge could swap its ends, or the import
record could lose its hash without failing anything. Each case compares the
written records whole.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline.control.contracts import ControlError, digest
from agentic_discipline.control.migration import import_legacy
from agentic_discipline.requirements import validate_requirement_graph

GRAPH: dict[str, Any] = {
    "feature_id": "billing",
    "nodes": [
        {"id": "REQ-1", "type": "requirement", "meta": {"title": "Invoices"}},
        {"id": "SPEC-1", "type": "spec", "path": None},
        {"id": "ACC-1", "type": "acceptance"},
        {"id": "TASK-1", "type": "task"},
        {"id": "TEST-1", "type": "test"},
        {"id": "CODE-1", "type": "code"},
        {"id": "EVID-1", "type": "evidence"},
    ],
    "edges": [
        {"from": "REQ-1", "to": "SPEC-1", "relation": "specified_by"},
        {"from": "ACC-1", "to": "TEST-1", "relation": "verified_by"},
        {"from": "REQ-1", "to": "TASK-1", "relation": "planned_by"},
        {"from": "TASK-1", "to": "CODE-1", "relation": "implemented_by"},
        {"from": "CODE-1", "to": "EVID-1", "relation": "evidenced_by"},
    ],
}

GRAPH_OF_TYPE = {
    "requirement": "requirement",
    "spec": "requirement",
    "acceptance": "requirement",
    "task": "execution",
    "test": "evidence",
    "code": "code",
    "evidence": "evidence",
}


def _write(path: Path, graph: dict[str, Any]) -> Path:
    path.write_text(json.dumps(graph), encoding="utf-8")
    return path


def _state(project: Any) -> tuple[Any, ...]:
    edges = project.store.db.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    return (
        project.store.knowledge_version,
        len(project.store.list("entity")),
        len(project.store.list("import")),
        edges,
    )


def test_import_writes_historical_entities_edges_and_its_record(project: Any) -> None:
    path = _write(project.root / "legacy.json", GRAPH)
    original = path.read_bytes()
    version = project.store.knowledge_version
    source = str(path.resolve())

    result = import_legacy(project, path)

    mapping = result["mapping"]
    assert result == {
        "mapping": mapping,
        "disposition": "HISTORICAL_REVIEW_REQUIRED",
        "original_unchanged": True,
    }
    assert list(mapping) == [node["id"] for node in GRAPH["nodes"]]
    assert len(set(mapping.values())) == len(GRAPH["nodes"])
    for node in GRAPH["nodes"]:
        stored = project.store.get(mapping[node["id"]], "entity")
        assert stored["id"].startswith("ENT-")
        assert stored == {
            "id": stored["id"],
            "version": 1,
            "graph": GRAPH_OF_TYPE[node["type"]],
            "type": node["type"],
            "name": node["id"],
            "source_ref": source,
            "authority": "historical",
            "observation": "DECLARED",
            "confidence": 0.5,
            "lifecycle": "HISTORICAL",
            "stale": False,
            "legacy_id": node["id"],
            "legacy_payload": node,
        }
        # All entities belong to the single knowledge revision the import opened.
        assert [h["knowledge_version"] for h in project.store.history(stored["id"])] == [
            version + 1
        ]

    rows = [dict(r) for r in project.store.db.execute("SELECT * FROM edges")]
    assert all(row["id"].startswith("EDGE-") for row in rows)
    assert sorted((r["source"], r["target"], r["relation"]) for r in rows) == sorted(
        (mapping[e["from"]], mapping[e["to"]], e["relation"]) for e in GRAPH["edges"]
    )

    (record,) = project.store.list("import")
    assert record == {
        "id": record["id"],
        "version": 1,
        "source": source,
        "source_hash": digest(GRAPH),
        "mapping": mapping,
        "disposition": "HISTORICAL_REVIEW_REQUIRED",
    }
    assert project.store.knowledge_version == version + 1
    assert path.read_bytes() == original


def test_dry_run_describes_the_import_without_writing(project: Any) -> None:
    path = _write(project.root / "legacy.json", GRAPH)
    before = _state(project)

    assert import_legacy(project, path, dry_run=True) == {
        "dry_run": True,
        "nodes": 7,
        "edges": 5,
        "source": str(path.resolve()),
        "writes": ["knowledge database"],
        "original_unchanged": True,
    }
    assert _state(project) == before


def test_same_graph_is_imported_once_whatever_its_path(project: Any) -> None:
    first = import_legacy(project, _write(project.root / "legacy.json", GRAPH))
    before = _state(project)
    copy = _write(project.root / "copy.json", GRAPH)

    expected = {"already_imported": True, "mapping": first["mapping"]}
    assert import_legacy(project, copy) == expected
    assert import_legacy(project, copy, dry_run=True) == expected
    assert _state(project) == before


def test_changed_graph_is_a_new_import(project: Any) -> None:
    path = _write(project.root / "legacy.json", GRAPH)
    first = import_legacy(project, path)
    changed = {**GRAPH, "nodes": [*GRAPH["nodes"], {"id": "REQ-2", "type": "requirement"}]}

    second = import_legacy(project, _write(path, changed))

    assert set(second["mapping"]) == set(first["mapping"]) | {"REQ-2"}
    assert not set(second["mapping"].values()) & set(first["mapping"].values())
    assert sorted(r["source_hash"] for r in project.store.list("import")) == sorted(
        [digest(GRAPH), digest(changed)]
    )


def test_invalid_graph_is_refused_with_every_error(project: Any) -> None:
    graph = {
        "feature_id": "broken",
        "nodes": [{"id": "REQ-1", "type": "requirement"}],
        "edges": [
            {"from": "REQ-1", "to": "REQ-1", "relation": "depends_on"},
            {"from": "GHOST", "to": "REQ-1", "relation": "depends_on"},
        ],
    }
    errors = validate_requirement_graph(graph)
    assert len(errors) >= 2
    before = _state(project)

    with pytest.raises(ControlError) as caught:
        import_legacy(project, _write(project.root / "legacy.json", graph))

    assert (caught.value.code, str(caught.value)) == ("INVALID_LEGACY_GRAPH", "; ".join(errors))
    assert _state(project) == before
