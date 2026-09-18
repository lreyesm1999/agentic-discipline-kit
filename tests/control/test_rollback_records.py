"""Knowledge changeset rollback, record by record.

A rollback rewrites knowledge that agents already reasoned from, so it must restore
exactly the previous revision, retire what the changeset created, refuse to
overwrite later work or resurrect retired intent, and write nothing when it
refuses. Existing tests checked one restored name and one refusal by message
fragment. Each case here compares the written records whole.
"""

from __future__ import annotations

from typing import Any

import pytest
from test_kernel import entity

from agentic_discipline.control.contracts import ControlError
from agentic_discipline.control.migration import rollback_changeset


def _apply(project: Any, reason: str, *changes: dict[str, Any]) -> dict[str, Any]:
    return project.knowledge.apply(list(changes), project.store.knowledge_version, reason)


def _update(record: dict[str, Any], **fields: Any) -> dict[str, Any]:
    return {**record, **fields, "expected_version": record["version"]}


def _refused(project: Any, identifier: str, reason: str) -> tuple[str, str]:
    with pytest.raises(ControlError) as caught:
        rollback_changeset(project, identifier, reason)
    return caught.value.code, str(caught.value)


def _snapshot(project: Any) -> tuple[Any, ...]:
    return (
        project.store.knowledge_version,
        project.store.list("entity"),
        project.store.list("changeset"),
    )


def test_rollback_restores_the_previous_revision_and_records_itself(project: Any) -> None:
    (created,) = _apply(project, "create", entity("Orders"))["entities"]
    rename = _apply(project, "rename", _update(created, name="Invoices"))
    version = project.store.knowledge_version

    result = rollback_changeset(project, rename["changeset"]["id"], "undo rename")

    assert result["id"].startswith("CHAN-")
    assert result == {
        **rename["changeset"],
        "version": 2,
        "status": "ROLLED_BACK",
        "rollback_reason": "undo rename",
    }
    assert project.store.get(result["id"], "changeset") == result
    assert project.store.get(created["id"], "entity") == {**created, "version": 3}
    history = project.store.history(created["id"])
    assert [h["knowledge_version"] for h in history] == [version - 1, version, version + 1]
    assert history[2]["payload"] == history[0]["payload"]
    assert project.store.knowledge_version == version + 1


def test_rolling_back_the_latest_rename_restores_the_one_before_it(project: Any) -> None:
    (created,) = _apply(project, "create", entity("Orders"))["entities"]
    (first,) = _apply(project, "rename", _update(created, name="Invoices"))["entities"]
    second = _apply(project, "rename again", _update(first, name="Payments"))

    rollback_changeset(project, second["changeset"]["id"], "undo second rename")

    assert project.store.get(created["id"], "entity") == {**first, "version": 4}


def test_rollback_retires_what_the_changeset_created(project: Any) -> None:
    change = _apply(project, "create", entity("Orders"), entity("Invoices", graph="architecture"))

    rollback_changeset(project, change["changeset"]["id"], "never needed")

    for created in change["entities"]:
        assert project.store.get(created["id"], "entity") == {
            **created,
            "version": 2,
            "lifecycle": "HISTORICAL",
            "lifecycle_reason": "never needed",
        }


def test_knowledge_retired_together_with_its_dependents_is_allowed(project: Any) -> None:
    active_dependent, active_upstream = _apply(
        project, "kept", entity("kept dependent"), entity("kept upstream")
    )["entities"]
    project.knowledge.link(active_dependent["id"], active_upstream["id"], "depends_on")
    change = _apply(project, "create", entity("dependent"), entity("upstream"))
    dependent, upstream = change["entities"]
    project.knowledge.link(dependent["id"], upstream["id"], "depends_on")

    result = rollback_changeset(project, change["changeset"]["id"], "drop both")

    assert result["status"] == "ROLLED_BACK"
    for created in (dependent, upstream):
        assert project.store.get(created["id"], "entity")["lifecycle"] == "HISTORICAL"


def test_rollback_refuses_to_leave_active_dependents_and_writes_nothing(project: Any) -> None:
    base = _apply(project, "base", entity("base requirement"))
    (target,) = base["entities"]
    (dependent,) = _apply(project, "later", entity("dependent"))["entities"]
    project.knowledge.link(dependent["id"], target["id"], "depends_on")
    before = _snapshot(project)

    assert _refused(project, base["changeset"]["id"], "remove base") == (
        "RETIRED_DEPENDENCY",
        "Rollback would retire knowledge with active dependents",
    )
    assert _snapshot(project) == before


def test_rollback_refuses_to_resurrect_retired_intent(project: Any) -> None:
    (created,) = _apply(project, "create", entity("Orders"))["entities"]
    retire = _apply(project, "retire", _update(created, lifecycle="RETIRED"))
    before = _snapshot(project)

    assert _refused(project, retire["changeset"]["id"], "bring it back") == (
        "RESURRECTION_BLOCKED",
        "Restoring active intent requires explicit replacement review",
    )
    assert _snapshot(project) == before


def test_retired_knowledge_may_roll_back_to_an_earlier_retired_revision(project: Any) -> None:
    (created,) = _apply(project, "create", entity("Orders"))["entities"]
    (retired,) = _apply(project, "retire", _update(created, lifecycle="RETIRED"))["entities"]
    rename = _apply(project, "rename", _update(retired, name="Old orders"))

    rollback_changeset(project, rename["changeset"]["id"], "keep the old name")

    assert project.store.get(created["id"], "entity") == {**retired, "version": 4}


def test_rollback_refuses_to_overwrite_later_work_in_any_entity(project: Any) -> None:
    change = _apply(project, "create", entity("Orders"), entity("Invoices"))
    untouched, later = change["entities"]
    _apply(project, "later edit", _update(later, name="Payments"))
    before = _snapshot(project)

    assert _refused(project, change["changeset"]["id"], "undo") == (
        "VERSION_CONFLICT",
        "Entity changed after this changeset",
    )
    assert _snapshot(project) == before
    assert project.store.get(untouched["id"], "entity") == untouched


def test_only_applied_changesets_can_be_rolled_back(project: Any) -> None:
    change = _apply(project, "create", entity("Orders"))
    rollback_changeset(project, change["changeset"]["id"], "undo")
    before = _snapshot(project)

    assert _refused(project, change["changeset"]["id"], "undo again") == (
        "INVALID_CHANGESET",
        "Changeset is not applied",
    )
    entity_id = change["entities"][0]["id"]
    assert _refused(project, entity_id, "undo") == ("NOT_FOUND", f"Record not found: {entity_id}")
    assert _snapshot(project) == before


@pytest.mark.parametrize("reason", ["", "   "])
def test_rollback_requires_a_reason_before_reading_anything(project: Any, reason: str) -> None:
    assert _refused(project, "CHAN-missing", reason) == (
        "REASON_REQUIRED",
        "Rollback requires a reason",
    )
