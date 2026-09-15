"""Task creation and plan audit, record by record.

`create_task` turns a reviewed contract into the task record every later step reads,
and `audit_plan` tells an agent whether a plan is ready to become that contract.
Existing tests checked a state or a status, so server fields could be initialized
wrongly, a stale requirement could slip through, or the audit could misreport a
missing dimension unnoticed. Each case compares the whole record or report.
"""

from __future__ import annotations

import json
import time
from typing import Any

import pytest
from conftest import contract
from test_kernel import entity

from agentic_discipline.control.contracts import ControlError, task_contract

DIMENSIONS = (
    "objective",
    "scope",
    "out_of_scope",
    "acceptance",
    "dependencies",
    "boundaries",
    "context",
    "verification",
    "required_evidence",
    "rollback",
    "definition_of_done",
    "risk",
    "budget",
)
ASK_LAST = [
    "canonical knowledge",
    "source",
    "tests",
    "current docs",
    "history",
    "reversible convention",
    "experiment",
    "human decision",
]


def _force(project: Any, kind: str, identifier: str, **fields: Any) -> dict[str, Any]:
    with project.store.transaction():
        current = project.store.get(identifier, kind)
        return project.store.put(kind, {**current, **fields}, expected=current["version"])


def _requirement(project: Any, name: str = "Orders") -> dict[str, Any]:
    (created,) = project.knowledge.apply([entity(name)], project.store.knowledge_version, "setup")[
        "entities"
    ]
    return created


def _rejects(project: Any, data: dict[str, Any], code: str, message: str) -> None:
    tasks = project.store.list("task")
    with pytest.raises(ControlError) as caught:
        project.create_task(data)
    assert (caught.value.code, str(caught.value)) == (code, message)
    assert project.store.list("task") == tasks


# --- create_task ----------------------------------------------------------------------------


def test_created_task_initializes_every_server_field(project: Any) -> None:
    requirement = _requirement(project)
    dependency = project.create_task(contract())
    data = {**contract(), "requirements": [requirement["id"]], "dependencies": [dependency["id"]]}
    version = project.store.knowledge_version

    before = time.time()
    task = project.create_task(data)
    after = time.time()

    assert task["id"].startswith("TASK-")
    assert task == {
        **data,
        "id": task["id"],
        "version": 1,
        "state": "PLANNED",
        "knowledge_version": version,
        "created_at": task["created_at"],
        "attempts": 0,
        "blocker": None,
        "workspace_id": None,
    }
    assert before <= task["created_at"] <= after
    assert project.store.get(task["id"], "task") == task
    (event,) = [
        json.loads(row["payload"])
        for row in project.store.db.execute(
            "SELECT payload FROM events WHERE action='task.write' ORDER BY seq"
        )
        if json.loads(row["payload"])["id"] == task["id"]
    ]
    assert event["version"] == 1


@pytest.mark.parametrize(
    ("change", "reason"),
    [({"lifecycle": "RETIRED"}, "retired"), ({"stale": True}, "stale")],
)
def test_tasks_cannot_rest_on_inactive_or_stale_requirements(
    project: Any, change: dict[str, Any], reason: str
) -> None:
    requirement = _requirement(project)
    _force(project, "entity", requirement["id"], **change)
    _rejects(
        project,
        {**contract(), "requirements": [requirement["id"]]},
        "STALE_REQUIREMENT",
        "Task refers to inactive or stale knowledge",
    )


def test_requirements_and_dependencies_must_be_records_of_their_kind(project: Any) -> None:
    requirement = _requirement(project)
    task = project.create_task(contract())
    for data, missing in (
        ({"requirements": ["ENT-missing"]}, "ENT-missing"),
        ({"requirements": [task["id"]]}, task["id"]),
        ({"dependencies": ["TASK-missing"]}, "TASK-missing"),
        ({"dependencies": [requirement["id"]]}, requirement["id"]),
    ):
        _rejects(project, {**contract(), **data}, "NOT_FOUND", f"Record not found: {missing}")


def test_every_requirement_is_checked_not_only_the_first(project: Any) -> None:
    active, retired = _requirement(project, "active"), _requirement(project, "retired")
    _force(project, "entity", retired["id"], lifecycle="RETIRED")
    _rejects(
        project,
        {**contract(), "requirements": [active["id"], retired["id"]]},
        "STALE_REQUIREMENT",
        "Task refers to inactive or stale knowledge",
    )


# --- audit_plan -----------------------------------------------------------------------------


def _full_plan(**changes: Any) -> dict[str, Any]:
    return {**contract(), "dependencies": ["TASK-upstream"], "context": ["docs/spec.md"], **changes}


def test_complete_plan_is_ready_to_become_a_task(project: Any) -> None:
    assert project.audit_plan(_full_plan()) == {
        "dimensions": dict.fromkeys(DIMENSIONS, "COVERED"),
        "issues": [],
        "status": "READY",
        "ask_last": ASK_LAST,
        "next_action": "Create task",
    }


def test_lists_the_contract_allows_empty_are_covered_once_stated(project: Any) -> None:
    plan = _full_plan(out_of_scope=[], dependencies=[], boundaries=[], context=[])
    report = project.audit_plan(plan)
    assert report["dimensions"] == dict.fromkeys(DIMENSIONS, "COVERED")
    assert (report["issues"], report["status"], report["next_action"]) == (
        [],
        "READY",
        "Create task",
    )


def _contract_issue(plan: dict[str, Any]) -> dict[str, str]:
    with pytest.raises(ControlError) as caught:
        task_contract(plan)
    return {"code": caught.value.code, "message": str(caught.value)}


def test_empty_plan_reports_every_missing_dimension_and_the_contract_issue(project: Any) -> None:
    assert project.audit_plan({}) == {
        "dimensions": dict.fromkeys(DIMENSIONS, "MISSING"),
        "issues": [_contract_issue({})],
        "status": "BLOCKED",
        "ask_last": ASK_LAST,
        "next_action": "Resolve missing contract fields from project sources",
    }


def test_blank_values_required_lists_and_absent_keys_are_missing(project: Any) -> None:
    plan = {k: v for k, v in _full_plan(rollback="", scope=[]).items() if k != "context"}
    report = project.audit_plan(plan)
    assert report["dimensions"] == {
        **dict.fromkeys(DIMENSIONS, "COVERED"),
        "rollback": "MISSING",
        "scope": "MISSING",
        "context": "MISSING",
    }
    assert report["issues"] == [_contract_issue(plan)]
    assert (report["status"], report["next_action"]) == (
        "BLOCKED",
        "Resolve missing contract fields from project sources",
    )


def test_a_dimension_can_be_covered_while_the_contract_is_still_invalid(project: Any) -> None:
    plan = _full_plan(risk="EXTREME")
    report = project.audit_plan(plan)
    assert report["dimensions"] == dict.fromkeys(DIMENSIONS, "COVERED")
    assert report["issues"] == [_contract_issue(plan)]
    assert report["status"] == "BLOCKED"
