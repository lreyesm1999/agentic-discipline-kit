"""Behavioral gaps identified by the verification mutation campaign."""

import time

from conftest import checkpoint, contract
from test_execution import setup_task
from test_kernel import entity

from agentic_discipline.control.verification import complete, invalidate, verify


def test_completion_selects_latest_checkpoint_and_records_released_ownership(project):
    task, session = setup_task(project)
    first = project.checkpoint(task, session, checkpoint())
    second = project.checkpoint(task, session, {**checkpoint(), "next_action": "Complete"})
    assert second["payload"]["timestamp"] >= first["payload"]["timestamp"]
    assert verify(project, task, session)["status"] == "PASS"
    before = time.time()
    result = complete(project, task, session)
    assert before <= result["completed_at"] <= time.time()
    assert all(lease["state"] == "RELEASED" for lease in project.store.list("lease"))


def test_unexecuted_tasks_do_not_stop_later_evidence_invalidation(project):
    data = contract()
    project.approve_command(data["verification"][0]["command"])
    tasks = sorted(project.create_task(data)["id"] for _ in range(3))
    task = tasks[-1]
    project.ready(task)
    session = project.join("worker", ["code"])["session"]
    project.claim(task, session)
    project.checkpoint(task, session, checkpoint())
    evidence = verify(project, task, session)["evidence"][0]
    complete(project, task, session)
    (project.root / "app.py").write_text("value = 2\n")
    result = invalidate(project)
    assert evidence["id"] in result["invalidated"]
    assert project.store.get(task)["state"] == "NEEDS_REVALIDATION"
    assert all(project.store.get(t)["state"] == "PLANNED" for t in tasks[:-1])


def test_retiring_requirement_invalidates_its_canonical_claim(project):
    node = project.knowledge.apply(
        [entity("retiring intent")], project.store.knowledge_version, "contract"
    )["entities"][0]
    claim = project.knowledge.claim(
        {
            "subject": node["id"],
            "predicate": "enabled",
            "value": True,
            "source_ref": "owner decision",
            "authority": "human",
            "confidence": 1,
            "observation": "DECLARED",
        }
    )
    invalidate(project)
    assert project.store.get(claim["id"])["disposition"] == "CANONICAL"
    project.knowledge.lifecycle(node["id"], "RETIRED", "requirement withdrawn")
    invalidate(project)
    assert project.store.get(claim["id"])["disposition"] == "STALE"


def test_retired_requirement_revokes_completed_proof(project):
    from agentic_discipline.control.verification import proof_current

    node = project.knowledge.apply(
        [entity("now-retired requirement")], project.store.knowledge_version, "contract"
    )["entities"][0]
    data = contract()
    data["requirements"] = [node["id"]]
    project.approve_command(data["verification"][0]["command"])
    task = project.create_task(data)["id"]
    project.ready(task)
    session = project.join("worker", ["code"])["session"]
    project.claim(task, session)
    project.checkpoint(task, session, checkpoint())
    assert verify(project, task, session)["status"] == "PASS"
    complete(project, task, session)
    assert proof_current(project, project.store.get(task))
    project.knowledge.lifecycle(node["id"], "RETIRED", "requirement removed")
    assert not proof_current(project, project.store.get(task))
    invalidate(project)
    assert project.store.get(task)["state"] == "NEEDS_REVALIDATION"
