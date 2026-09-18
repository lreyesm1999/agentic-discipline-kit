from unittest.mock import patch

import pytest
from conftest import checkpoint, contract
from test_execution import setup_task
from test_kernel import entity

from agentic_discipline.control.api import call
from agentic_discipline.control.contracts import ControlError
from agentic_discipline.control.verification import complete, invalidate, verify


def test_interrupted_execution_releases_run_and_preserves_checkpoint(project):
    task, session = setup_task(project)
    project.checkpoint(task, session, checkpoint())
    with patch(
        "agentic_discipline.control.verification.run_gate",
        side_effect=OSError("executor unavailable"),
    ):
        with pytest.raises(OSError):
            verify(project, task, session)
    state = project.store.get(task)
    assert state["state"] == "FAILED" and state["active_run"] is None
    assert project.resume(task, session)["mandatory"]["checkpoint"]
    assert verify(project, task, session)["status"] == "PASS"
    assert complete(project, task, session)["state"] == "COMPLETED"


def test_owner_resolves_blocker_and_records_terminal_disposition(project):
    task, session = setup_task(project)
    project.release(task, session, "Choose a retention period")
    with pytest.raises(ControlError):
        project.ready(task)
    with pytest.raises(ControlError):
        call(project, "resolve_blocker", {"task_id": task, "decision": "Thirty days"})
    call(project, "resolve_blocker", {"task_id": task, "decision": "Thirty days"}, local=True)
    assert project.ready(task)["state"] == "READY"
    assert project.context(task)["mandatory"]["decisions"][0]["decision"] == "Thirty days"
    project.claim(task, session)
    assert (
        call(
            project,
            "task_transition",
            {"task_id": task, "state": "CANCELLED", "reason": "Scope removed"},
            local=True,
        )["data"]["state"]
        == "CANCELLED"
    )
    with pytest.raises(ControlError):
        project.owned(task, session)
    with pytest.raises(ControlError):
        project.ready(task)


def test_dependency_evidence_and_canonical_claim_invalidate_live(project):
    node = project.knowledge.apply(
        [entity("value requirement")], project.store.knowledge_version, "contract"
    )["entities"][0]
    data = contract()
    data["requirements"] = [node["id"]]
    project.approve_command(data["verification"][0]["command"])
    first = project.create_task(data)["id"]
    project.ready(first)
    session = project.join("builder", ["code", "terminal"])["session"]
    project.claim(first, session)
    project.checkpoint(first, session, checkpoint())
    evidence = verify(project, first, session)["evidence"][0]
    complete(project, first, session)
    claim = project.knowledge.claim(
        {
            "subject": node["id"],
            "predicate": "verified",
            "value": True,
            "source_ref": "test_app.py",
            "authority": "verified",
            "confidence": 1,
            "observation": "VERIFIED",
            "evidence_refs": [evidence["id"]],
            "acceptance_index": 0,
        }
    )
    dependent = project.create_task({**data, "dependencies": [first]})["id"]
    project.ready(dependent)
    project.claim(dependent, session)
    project.checkpoint(dependent, session, checkpoint())
    verify(project, dependent, session)
    complete(project, dependent, session)
    (project.root / "app.py").write_text("value = 2\n")
    third = project.create_task({**data, "dependencies": [dependent]})["id"]
    assert project.readiness(third)["status"] == "BLOCKED"
    invalidate(project)
    assert project.store.get(first)["state"] == "NEEDS_REVALIDATION"
    assert project.store.get(dependent)["state"] == "NEEDS_REVALIDATION"
    assert project.store.get(claim["id"])["disposition"] == "STALE"


def test_temporal_queries_retirement_and_owner_claim_resolution(project):
    nodes = project.knowledge.apply(
        [entity("upstream"), entity("dependent")], project.store.knowledge_version, "requirements"
    )["entities"]
    revision = project.store.knowledge_version
    project.knowledge.link(nodes[1]["id"], nodes[0]["id"], "depends_on")
    with pytest.raises(ControlError, match="Retire or replace"):
        project.knowledge.lifecycle(nodes[0]["id"], "RETIRED", "removed")
    node = nodes[0]
    left = project.knowledge.claim(
        {
            "subject": node["id"],
            "predicate": "period",
            "value": 30,
            "source_ref": "human brief",
            "authority": "human",
            "confidence": 1,
            "observation": "DECLARED",
        }
    )
    project.knowledge.claim(
        {
            "subject": node["id"],
            "predicate": "period",
            "value": 60,
            "source_ref": "second brief",
            "authority": "human",
            "confidence": 1,
            "observation": "DECLARED",
        }
    )
    assert project.store.get(left["id"])["disposition"] == "CONFLICTING"
    chosen = call(
        project,
        "resolve_claim",
        {"identifier": left["id"], "reason": "Confirmed thirty days"},
        local=True,
    )["data"]
    assert chosen["disposition"] == "CANONICAL" and chosen["authority"] == "human"
    assert not any(c["disposition"] == "CONFLICTING" for c in project.store.list("claim"))
    project.knowledge.lifecycle(nodes[1]["id"], "RETIRED", "remove dependent first")
    project.knowledge.lifecycle(node["id"], "RETIRED", "remove upstream")
    historical = call(project, "query_knowledge", {"graph": "requirement", "at_version": revision})[
        "data"
    ]
    assert {n["id"] for n in historical} == {n["id"] for n in nodes}
    assert not project.knowledge.query(graph="requirement")


def test_mandatory_decisions_failure_output_and_deleted_line_budget(project):
    project.knowledge.apply(
        [{**entity("Keep local data"), "graph": "decision", "authority": "human"}],
        project.store.knowledge_version,
        "human constraint",
    )
    task, session = setup_task(project)
    assert project.context(task)["mandatory"]["protected_decisions"][0]["name"] == "Keep local data"
    (project.root / "app.py").write_text("value = 0\n")
    assert verify(project, task, session)["status"] == "FAIL"
    context = project.context(task)
    assert "AssertionError" in context["mandatory"]["current_failures"][0]["output"]["stderr"]
    project.release(task, session)
    (project.root / "large.py").write_text("x = 1\n" * 101)
    data = contract()
    data["scope"] = ["large.py"]
    second = project.create_task(data)["id"]
    project.ready(second)
    project.claim(second, session)
    (project.root / "large.py").unlink()
    with pytest.raises(ControlError, match="line budget"):
        verify(project, second, session)


def test_checkpoint_hash_required_for_completion_and_state_injection_refused(project):
    for field in ("proof", "active_run", "initial_files", "runtime_used"):
        with pytest.raises(ControlError, match="server-owned"):
            project.create_task({**contract(), field: {}})
    task, session = setup_task(project)
    cp = project.checkpoint(task, session, checkpoint())
    verify(project, task, session)
    with project.store.transaction():
        project.store.put("checkpoint", {**cp, "content_hash": "changed"}, expected=cp["version"])
    with pytest.raises(ControlError, match="hash"):
        complete(project, task, session)


def test_rollback_cannot_retire_a_newly_referenced_requirement(project):
    from agentic_discipline.control.migration import rollback_changeset

    change = project.knowledge.apply(
        [entity("base requirement")], project.store.knowledge_version, "base"
    )
    target = change["entities"][0]["id"]
    dependent = project.knowledge.apply(
        [entity("dependent")], project.store.knowledge_version, "later requirement"
    )["entities"][0]["id"]
    project.knowledge.link(dependent, target, "depends_on")
    version = project.store.knowledge_version
    with pytest.raises(ControlError, match="active dependents"):
        rollback_changeset(project, change["changeset"]["id"], "remove base")
    assert project.store.get(target)["lifecycle"] == "ACTIVE"
    assert project.store.knowledge_version == version
