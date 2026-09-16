import time
from pathlib import Path

import pytest
from conftest import checkpoint, contract

from agentic_discipline.control.contracts import ControlError
from agentic_discipline.control.plane import Plane, adopt
from agentic_discipline.control.verification import complete, invalidate, verify


def setup_task(plane):
    data = contract()
    plane.approve_command(data["verification"][0]["command"])
    task = plane.create_task(data)
    plane.ready(task["id"])
    worker = plane.join("worker", ["code", "terminal"])
    plane.claim(task["id"], worker["session"])
    return task["id"], worker["session"]


def test_adoption_dry_run_preserves_user_files_and_ignores_secrets(tmp_path: Path):
    (tmp_path / "AGENTS.md").write_text("Existing instructions")
    (tmp_path / ".env").write_text("API_KEY=do-not-read-this-value")
    report = adopt(tmp_path, True)
    assert not (tmp_path / ".agentic").exists()
    assert [i["path"] for i in report["files"]] == ["AGENTS.md"]
    adopt(tmp_path)
    assert (tmp_path / "AGENTS.md").read_text() == "Existing instructions"
    assert adopt(tmp_path)["already_adopted"]


def test_complete_requires_proof_then_external_edit_invalidates(project):
    task, session = setup_task(project)
    with pytest.raises(ControlError):
        complete(project, task, session)
    project.checkpoint(task, session, checkpoint())
    assert verify(project, task, session)["status"] == "PASS"
    assert complete(project, task, session)["state"] == "COMPLETED"
    (project.root / "app.py").write_text("value = 2\n")
    report = project.reconcile()
    assert report["invalidated"]
    assert project.store.get(task)["state"] == "NEEDS_REVALIDATION"
    assert project.store.audit()["status"] == "PASS"


def test_session_restart_and_lease_expiry_preserve_checkpoint(project):
    task, session = setup_task(project)
    saved = project.checkpoint(task, session, checkpoint())
    with pytest.raises(ControlError):
        project.claim(task, project.join("other", ["terminal"])["session"])
    with project.store.transaction():
        lease = project.owned(task, session)[1]
        project.store.put(
            "lease", {**lease, "expires_at": time.time() - 1}, expected=lease["version"]
        )
    with Plane(project.root) as second:
        worker = second.join("replacement", ["terminal"])
        second.claim(task, worker["session"])
        resumed = second.resume(task, worker["session"])
        assert resumed["mandatory"]["checkpoint"]["id"] == saved["id"]
        assert not resumed["baseline_changed"]
        with pytest.raises(ControlError):
            second.heartbeat(task, session)


def test_failed_tampered_and_unknown_evidence_never_complete(project):
    task, session = setup_task(project)
    project.checkpoint(task, session, checkpoint())
    proof = verify(project, task, session)["evidence"][0]
    artifact = project.directory / "evidence" / (proof["id"] + ".json")
    artifact.write_text("tampered")
    with pytest.raises(ControlError, match="tampered"):
        complete(project, task, session)
    assert invalidate(project)["invalidated"]
    (project.root / "app.py").write_text("value = 2\n")
    assert verify(project, task, session)["status"] == "FAIL"
    with pytest.raises(ControlError):
        complete(project, task, session)


def test_context_never_truncates_mandatory_and_corruption_detected(project):
    task, session = setup_task(project)
    saved = project.checkpoint(task, session, checkpoint())
    with pytest.raises(ControlError, match="Mandatory context"):
        project.context(task, 10)
    with project.store.transaction():
        project.store.put("checkpoint", {**saved, "content_hash": "bad"}, expected=saved["version"])
    with pytest.raises(ControlError, match="Checkpoint content"):
        project.resume(task, session)


def test_unapproved_commands_scope_and_credentials_rejected(project):
    task = project.create_task(contract())
    assert project.readiness(task["id"])["status"] == "BLOCKED"
    with pytest.raises(ControlError):
        project.ready(task["id"])
    with pytest.raises(ControlError):
        project.create_task({**contract(), "scope": ["../outside"]})
    with pytest.raises(ControlError):
        project.create_task({**contract(), "objective": "password=topsecret"})
