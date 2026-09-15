"""Knowledge changesets, record by record.

`Knowledge.apply` is the only way knowledge changes in bulk, and the changeset it
records is what rollback later reverses. Existing tests checked its refusals and a
renamed name, so the changeset record, the actor, the lifecycle defaults or the
all-or-nothing behavior of a refused changeset could change unnoticed. Each case
compares the written records whole.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from test_kernel import entity

from agentic_discipline.control.contracts import ControlError


def _apply(project: Any, *changes: dict[str, Any], **options: Any) -> dict[str, Any]:
    return project.knowledge.apply(list(changes), project.store.knowledge_version, **options)


def _snapshot(project: Any) -> tuple[Any, ...]:
    return (
        project.store.knowledge_version,
        project.store.list("entity"),
        project.store.list("changeset"),
    )


def _actors(project: Any, action: str) -> list[str]:
    rows = project.store.db.execute("SELECT actor, payload FROM events WHERE action = ?", (action,))
    return [row["actor"] for row in rows]


def test_applied_changeset_returns_its_record_entities_and_version(project: Any) -> None:
    version = project.store.knowledge_version
    first, second = entity("Orders"), {**entity("Payments", "architecture"), "stale": True}

    result = project.knowledge.apply([first, second], version, "import orders", actor="importer")

    created = result["entities"]
    assert [e["id"][:4] for e in created] == ["ENTI", "ENTI"]
    assert created == [
        {**first, "lifecycle": "ACTIVE", "stale": False, "id": created[0]["id"], "version": 1},
        {**second, "lifecycle": "ACTIVE", "id": created[1]["id"], "version": 1},
    ]
    changeset = result["changeset"]
    assert changeset["id"].startswith("CHAN-")
    assert result == {
        "changeset": {
            "id": changeset["id"],
            "version": 1,
            "base_version": version,
            "reason": "import orders",
            "actor": "importer",
            "entities": [created[0]["id"], created[1]["id"]],
            "status": "APPLIED",
        },
        "entities": created,
        "knowledge_version": version + 1,
    }
    assert project.store.get(changeset["id"], "changeset") == changeset
    assert project.store.knowledge_version == version + 1
    assert _actors(project, "entity.write")[-2:] == ["importer", "importer"]
    assert _actors(project, "changeset.write")[-1] == "importer"


def test_actor_defaults_to_local(project: Any) -> None:
    result = _apply(project, entity("Orders"), reason="seed")
    assert result["changeset"]["actor"] == "local"
    assert _actors(project, "changeset.write")[-1] == "local"


def test_explicit_lifecycle_is_kept_and_expected_version_is_not_stored(project: Any) -> None:
    (created,) = _apply(project, {**entity("Orders"), "lifecycle": "DEPRECATED"}, reason="seed")[
        "entities"
    ]
    assert created["lifecycle"] == "DEPRECATED"
    (updated,) = _apply(
        project, {**created, "name": "Orders v2", "expected_version": 1}, reason="rename"
    )["entities"]
    assert "expected_version" not in project.store.get(updated["id"], "entity")
    assert updated["version"] == 2
    row = project.store.db.execute(
        "SELECT payload FROM records WHERE id = ?", (updated["id"],)
    ).fetchone()
    assert "expected_version" not in json.loads(row["payload"])


def test_a_refused_change_writes_nothing_from_the_whole_changeset(project: Any) -> None:
    (existing,) = _apply(project, entity("Orders"), reason="seed")["entities"]
    before = _snapshot(project)
    with pytest.raises(ControlError) as caught:
        _apply(
            project,
            entity("New and valid"),
            {**existing, "name": "Renamed", "expected_version": 99},
            reason="bulk",
        )
    assert caught.value.code == "VERSION_CONFLICT"
    assert _snapshot(project) == before


def test_invalid_entities_roll_back_the_version_bump(project: Any) -> None:
    before = _snapshot(project)
    with pytest.raises(ControlError) as caught:
        _apply(project, entity("Valid"), {**entity("Bad"), "graph": "nowhere"}, reason="bulk")
    assert (caught.value.code, str(caught.value)) == ("INVALID_GRAPH", "Unknown specialized graph")
    assert _snapshot(project) == before


def test_retiring_a_dependency_together_with_its_dependents_is_allowed(project: Any) -> None:
    upstream, dependent = _apply(project, entity("upstream"), entity("dependent"), reason="seed")[
        "entities"
    ]
    project.knowledge.link(dependent["id"], upstream["id"], "depends_on")

    retired = _apply(
        project,
        {**upstream, "lifecycle": "RETIRED", "expected_version": 1},
        {**dependent, "lifecycle": "RETIRED", "expected_version": 1},
        reason="retire both",
    )["entities"]

    assert [e["lifecycle"] for e in retired] == ["RETIRED", "RETIRED"]


def test_retiring_only_the_dependency_is_refused_and_writes_nothing(project: Any) -> None:
    upstream, dependent = _apply(project, entity("upstream"), entity("dependent"), reason="seed")[
        "entities"
    ]
    project.knowledge.link(dependent["id"], upstream["id"], "depends_on")
    before = _snapshot(project)

    with pytest.raises(ControlError) as caught:
        _apply(
            project, {**upstream, "lifecycle": "RETIRED", "expected_version": 1}, reason="retire"
        )

    assert (caught.value.code, str(caught.value)) == (
        "RETIRED_DEPENDENCY",
        "Retire or replace active dependents in the same changeset",
    )
    assert _snapshot(project) == before


def test_only_depends_on_links_block_retirement(project: Any) -> None:
    requirement, code = _apply(
        project, entity("requirement"), entity("module", "code"), reason="seed"
    )["entities"]
    project.knowledge.link(requirement["id"], code["id"], "implemented_by")

    (retired,) = _apply(
        project, {**code, "lifecycle": "RETIRED", "expected_version": 1}, reason="remove module"
    )["entities"]

    assert retired["lifecycle"] == "RETIRED"
