"""References stored inside records are read with the kind they must have.

A task's workspace, requirements and dependencies, a lease's task, a claim's subject
and evidence, an evidence record's task, a changeset's entities and the edges table
all hold identifiers that the plane validated when it wrote them. Each read checks
the kind again, so a store edited outside the plane is refused instead of acted on.
Each case forges one such reference to point at a record of another kind and pins
the refusal: `NOT_FOUND` for that identifier, not a later error or a silent result.
"""

from __future__ import annotations

from typing import Any, Callable

import pytest
from conftest import contract
from test_kernel import entity

from agentic_discipline.control.contracts import ControlError
from agentic_discipline.control.migration import rollback_changeset
from agentic_discipline.control.verification import binding, invalidate
from agentic_discipline.control.workspaces import (
    cleanup,
    integration_gate,
    merge_workspace,
    refresh_workspace,
)


def _force(project: Any, kind: str, identifier: str, **fields: Any) -> dict[str, Any]:
    with project.store.transaction():
        current = project.store.get(identifier, kind)
        return project.store.put(kind, {**current, **fields}, expected=current["version"])


def _entity(project: Any, name: str = "Orders") -> dict[str, Any]:
    applied = project.knowledge.apply([entity(name)], project.store.knowledge_version, "seed")
    return dict(applied["entities"][0])


def _task(project: Any, **changes: Any) -> str:
    project.approve_command(contract()["verification"][0]["command"])
    return str(project.create_task({**contract(), **changes})["id"])


def _claimed(project: Any) -> tuple[str, str]:
    task = _task(project)
    project.ready(task)
    session = project.join("worker", ["code", "terminal"])["session"]
    project.claim(task, session)
    return task, session


def _refused(action: Callable[[], Any], identifier: str) -> None:
    with pytest.raises(ControlError) as caught:
        action()
    assert (caught.value.code, str(caught.value)) == (
        "NOT_FOUND",
        f"Record not found: {identifier}",
    )


# --- a task's workspace ---------------------------------------------------------------------


def test_a_workspace_reference_that_names_a_task_is_refused(project: Any) -> None:
    other = _task(project)
    task, session = _claimed(project)
    _force(project, "task", task, workspace_id=other)

    _refused(lambda: project.workspace_root(project.store.get(task, "task")), other)
    _refused(lambda: integration_gate(project, task, session), other)
    _refused(lambda: merge_workspace(project, task, session), other)


def test_cleanup_and_refresh_refuse_a_workspace_reference_that_names_a_task(
    project: Any,
) -> None:
    other = _task(project)
    idle = _task(project)
    _force(project, "task", idle, workspace_id=other)
    finished = _task(project)
    _force(project, "task", finished, workspace_id=other, state="CANCELLED")

    _refused(lambda: refresh_workspace(project, idle), other)
    _refused(lambda: cleanup(project, finished), other)


# --- a task's requirements and dependencies -------------------------------------------------


def test_a_requirement_reference_that_names_a_task_is_refused(project: Any) -> None:
    other = _task(project)
    task = _task(project)
    _force(project, "task", task, requirements=[other])

    _refused(lambda: project.readiness(task), other)
    _refused(lambda: project.context(task), other)
    _refused(lambda: binding(project, project.store.get(task, "task")), other)


def test_a_dependency_reference_that_names_knowledge_is_refused(project: Any) -> None:
    orders = _entity(project)
    task = _task(project)
    _force(project, "task", task, dependencies=[orders["id"]])

    _refused(lambda: project.readiness(task), orders["id"])
    _refused(lambda: binding(project, project.store.get(task, "task")), orders["id"])


# --- leases ---------------------------------------------------------------------------------


def test_another_active_lease_that_names_knowledge_is_refused(project: Any) -> None:
    orders = _entity(project)
    task, _ = _claimed(project)
    (lease,) = [item for item in project.store.list("lease") if item["task_id"] == task]
    _force(project, "lease", lease["id"], task_id=orders["id"])
    second = _task(project, scope=["test_app.py"])
    project.ready(second)
    session = project.join("second", ["code", "terminal"])["session"]

    _refused(lambda: project.claim(second, session), orders["id"])


# --- claims and evidence --------------------------------------------------------------------


def _claim(project: Any, subject: str) -> dict[str, Any]:
    return project.knowledge.claim(
        {
            "subject": subject,
            "predicate": "retention_days",
            "value": 30,
            "source_ref": "brief.md",
            "authority": "human",
            "confidence": 1,
            "observation": "DECLARED",
        }
    )


def test_a_claim_subject_that_names_a_task_is_refused(project: Any) -> None:
    orders = _entity(project)
    canonical = _claim(project, orders["id"])
    task = _task(project)
    _force(project, "claim", canonical["id"], subject=task)

    _refused(lambda: project.knowledge.resolve_claim(canonical["id"], "decided"), task)
    _refused(lambda: invalidate(project), task)


def test_claim_evidence_that_names_a_task_is_refused(project: Any) -> None:
    orders = _entity(project)
    canonical = _claim(project, orders["id"])
    task = _task(project)
    _force(project, "claim", canonical["id"], evidence_refs=[task])

    _refused(lambda: invalidate(project), task)


def test_evidence_whose_task_names_knowledge_is_refused(project: Any) -> None:
    from agentic_discipline.control.verification import verify

    task, session = _claimed(project)
    verify(project, task, session)
    (evidence,) = [e for e in project.store.list("evidence") if e["task_id"] == task]
    orders = _entity(project)
    _force(project, "evidence", evidence["id"], task_id=orders["id"])

    _refused(
        lambda: project.knowledge.claim(
            {
                "subject": orders["id"],
                "predicate": "retention_days",
                "value": 30,
                "source_ref": "brief.md",
                "authority": "code",
                "confidence": 1,
                "observation": "VERIFIED",
                "evidence_refs": [evidence["id"]],
            }
        ),
        orders["id"],
    )


# --- changesets and edges -------------------------------------------------------------------


def test_a_changeset_entity_that_names_a_task_is_refused(project: Any) -> None:
    _entity(project)
    (change,) = project.store.list("changeset")
    task = _task(project)
    _force(project, "changeset", change["id"], entities=[task])

    _refused(lambda: rollback_changeset(project, change["id"], "undo"), task)


def test_an_edge_that_names_a_task_is_refused(project: Any) -> None:
    orders = _entity(project)
    (change,) = project.store.list("changeset")
    task = _task(project)
    with project.store.transaction():
        project.store.db.execute(
            "INSERT INTO edges VALUES (?,?,?,?)", ("EDGE-forged", task, orders["id"], "depends_on")
        )

    _refused(
        lambda: project.knowledge.apply(
            [entity("Invoices")], project.store.knowledge_version, "add"
        ),
        task,
    )
    _refused(lambda: rollback_changeset(project, change["id"], "undo"), task)


def test_an_edge_whose_target_names_a_task_is_refused(project: Any) -> None:
    orders = _entity(project)
    (change,) = project.store.list("changeset")
    task = _task(project)
    with project.store.transaction():
        project.store.db.execute(
            "INSERT INTO edges VALUES (?,?,?,?)", ("EDGE-forged", orders["id"], task, "depends_on")
        )

    _refused(
        lambda: project.knowledge.apply(
            [entity("Invoices")], project.store.knowledge_version, "add"
        ),
        task,
    )
    _refused(lambda: rollback_changeset(project, change["id"], "undo"), task)
