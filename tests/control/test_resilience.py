import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest
from conftest import checkpoint, contract
from hypothesis import given
from hypothesis import strategies as st
from test_execution import setup_task
from test_kernel import entity

from agentic_discipline.control.api import call
from agentic_discipline.control.contracts import ControlError
from agentic_discipline.control.knowledge import Knowledge
from agentic_discipline.control.migration import rollback_changeset
from agentic_discipline.control.plane import Plane, adopt
from agentic_discipline.control.store import Store
from agentic_discipline.control.verification import complete, invalidate, verify


def test_concurrent_changesets_never_lose_a_write(tmp_path: Path):
    path = tmp_path / "state.db"
    with Store(path, create=True):
        pass
    barrier = threading.Barrier(2)

    def write(name):
        with Store(path) as store:
            barrier.wait()
            try:
                Knowledge(store).apply([entity(name)], 0, "race")
                return "OK"
            except ControlError as exc:
                return exc.code

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(write, ["A", "B"]))
    assert sorted(results) == ["OK", "VERSION_CONFLICT"]
    with Store(path) as store:
        assert len(store.list("entity")) == 1
        assert store.audit()["status"] == "PASS"


def test_new_low_authority_claim_cannot_demote_human_intent(project):
    subject = project.knowledge.apply([entity()], project.store.knowledge_version, "approved")[
        "entities"
    ][0]
    claim = dict(
        subject=subject["id"],
        predicate="enabled",
        value=True,
        source_ref="human decision",
        authority="human",
        confidence=1,
        observation="DECLARED",
    )
    canonical = project.knowledge.claim(claim)
    result = call(
        project,
        "record_discovery",
        {"data": {**claim, "value": False, "authority": "inference", "observation": "INFERRED"}},
    )
    assert result["data"]["disposition"] == "REJECTED"
    assert project.store.get(canonical["id"])["disposition"] == "CANONICAL"


def test_inflight_rerun_cannot_complete_using_prior_pass(project):
    task, session = setup_task(project)
    project.checkpoint(task, session, checkpoint())
    assert verify(project, task, session)["status"] == "PASS"
    from agentic_discipline.quality import run_gate as real_run

    entered, finish = threading.Event(), threading.Event()

    def blocking(*args, **kwargs):
        entered.set()
        assert finish.wait(3)
        result = real_run(*args, **kwargs)
        result.status = "FAIL"
        result.exit_code = 1
        return result

    def work():
        with Plane(project.root) as other:
            return verify(other, task, session)

    with (
        patch("agentic_discipline.control.verification.run_gate", blocking),
        ThreadPoolExecutor(1) as pool,
    ):
        future = pool.submit(work)
        assert entered.wait(3)
        with pytest.raises(ControlError):
            complete(project, task, session)
        with pytest.raises(ControlError, match="already running"):
            verify(project, task, session)
        finish.set()
        assert future.result()["status"] == "FAIL"
    assert project.store.get(task)["state"] == "FAILED"
    assert len(project.store.list("evidence")) == 2


def test_old_proof_does_not_invalidate_current_proof(project):
    task, session = setup_task(project)
    project.checkpoint(task, session, checkpoint())
    verify(project, task, session)
    (project.root / "app.py").write_text("value = 1\n# revised implementation\n")
    verify(project, task, session)
    complete(project, task, session)
    assert invalidate(project)["invalidated"]
    assert project.store.get(task)["state"] == "COMPLETED"


def test_failed_owner_expiry_recovers_and_overlapping_tasks_refused(project):
    task, session = setup_task(project)
    second = project.create_task(contract())
    project.ready(second["id"])
    agent = project.join("second", ["terminal"])
    with pytest.raises(ControlError, match="isolated"):
        project.claim(second["id"], agent["session"])
    (project.root / "app.py").write_text("raise RuntimeError('failed')\n")
    verify(project, task, session)
    with project.store.transaction():
        lease = project.owned(task, session)[1]
        project.store.put(
            "lease", {**lease, "expires_at": time.time() - 10}, expected=lease["version"]
        )
    assert project.claim(task, agent["session"])["agent_id"] == agent["id"]


def test_symlinked_evidence_and_control_paths_rejected(project, tmp_path: Path):
    task, session = setup_task(project)
    outside = tmp_path / "outside"
    outside.mkdir()
    (project.directory / "evidence").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ControlError, match="symlink"):
        verify(project, task, session)
    assert not list(outside.iterdir())


def test_generated_runtime_input_is_part_of_freshness(project):
    (project.root / "dist").mkdir()
    (project.root / "dist/value.txt").write_text("one")
    task, session = setup_task(project)
    project.checkpoint(task, session, checkpoint())
    verify(project, task, session)
    (project.root / "dist/value.txt").write_text("two")
    with pytest.raises(ControlError, match="stale"):
        complete(project, task, session)


def test_long_dependency_cycle_rejected_and_rollback_preserves_history(project):
    k = project.knowledge
    nodes = k.apply([entity(str(i)) for i in range(7)], project.store.knowledge_version, "chain")[
        "entities"
    ]
    for left, right in zip(nodes, nodes[1:], strict=False):
        k.link(left["id"], right["id"], "depends_on")
    with pytest.raises(ControlError, match="cycle"):
        k.link(nodes[-1]["id"], nodes[0]["id"], "depends_on")
    original = nodes[0]
    change = k.apply(
        [{**original, "name": "renamed", "expected_version": 1}],
        project.store.knowledge_version,
        "rename",
    )
    rollback_changeset(project, change["changeset"]["id"], "revert name")
    assert project.store.get(original["id"])["name"] == "0"
    assert len(project.store.history(original["id"])) == 3


def test_tampered_and_unrelated_claim_evidence_rejected(project):
    req = project.knowledge.apply([entity()], project.store.knowledge_version, "acceptance")[
        "entities"
    ][0]
    data = contract()
    data["requirements"] = [req["id"]]
    project.approve_command(data["verification"][0]["command"])
    task = project.create_task(data)
    project.ready(task["id"])
    worker = project.join("worker", ["terminal"])
    project.claim(task["id"], worker["session"])
    proof = verify(project, task["id"], worker["session"])["evidence"][0]
    claim = dict(
        subject=req["id"],
        predicate="criterion",
        value=True,
        source_ref="test",
        authority="verified",
        confidence=1,
        observation="VERIFIED",
        evidence_refs=[proof["id"]],
        acceptance_index=0,
    )
    assert project.knowledge.claim(claim)["disposition"] == "CANONICAL"
    (project.directory / "evidence" / (proof["id"] + ".json")).write_text("tampered")
    with pytest.raises(ControlError):
        project.knowledge.claim(claim)


@given(st.text(alphabet="abcdef 123", min_size=1, max_size=40))
def test_redaction_covers_quoted_secret_values(value):
    from agentic_discipline.control.contracts import redact

    output = redact(json.dumps({"password": value}))
    assert "[REDACTED]" in output


def test_json_credentials_never_enter_discovery_db(tmp_path: Path):
    (tmp_path / "settings.json").write_text(json.dumps({"password": "synthetic-password-123"}))
    adopt(tmp_path)
    with Plane(tmp_path) as plane:
        assert "synthetic-password-123" not in json.dumps(plane.store.list("entity"))


def test_invalid_proof_kind_missing_tool_budget_and_task_contract(project):
    data = contract()
    data["verification"][0]["command"] = ["nonexistent-agentic-test-command"]
    project.approve_command(data["verification"][0]["command"])
    task = project.create_task(data)
    project.ready(task["id"])
    worker = project.join("worker", ["terminal"])
    project.claim(task["id"], worker["session"])
    assert verify(project, task["id"], worker["session"])["evidence"][0]["result"] == "BLOCKED"
    with pytest.raises(ControlError):
        project.create_task({**contract(), "state": "COMPLETED"})
    assert project.audit_plan({})["status"] == "BLOCKED"
    assert project.audit_plan(contract())["status"] == "READY"
