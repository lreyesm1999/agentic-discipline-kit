import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from conftest import checkpoint, contract
from test_execution import setup_task
from test_kernel import entity
from test_workspaces import repository

from agentic_discipline.control import cli
from agentic_discipline.control.api import call
from agentic_discipline.control.contracts import ControlError
from agentic_discipline.control.mcp import Session
from agentic_discipline.control.plane import Plane
from agentic_discipline.control.verification import complete, invalidate, proof_current, verify
from agentic_discipline.control.workspaces import create_workspace, merge_workspace
from agentic_discipline.quality import GateResult


def test_retained_worktree_cannot_hide_broken_primary(tmp_path: Path):
    repository(tmp_path)
    with Plane(tmp_path) as plane:
        data = contract()
        plane.approve_command(data["verification"][0]["command"])
        task = plane.create_task(data)["id"]
        create_workspace(plane, task)
        plane.ready(task)
        session = plane.join("worker", ["code"])["session"]
        plane.claim(task, session)
        plane.checkpoint(task, session, checkpoint())
        verify(plane, task, session)
        merge_workspace(plane, task, session)
        complete(plane, task, session)
        (tmp_path / "app.py").write_text("value = 2\n")
        assert not proof_current(plane, plane.store.get(task))
        assert invalidate(plane)["invalidated"]
        assert plane.store.get(task)["state"] == "NEEDS_REVALIDATION"


def test_symlink_inputs_never_receive_current_proof(project):
    target = project.root.parent / (project.root.name + "-external.py")
    target.write_text("value = 1\n")
    (project.root / "external.py").symlink_to(target)
    task, session = setup_task(project)
    with pytest.raises(ControlError, match="Symlink"):
        verify(project, task, session)
    assert not project.store.list("evidence")


def test_protected_edits_are_checked_before_execution_and_at_completion(project):
    data = contract()
    data["scope"] = ["."]
    project.approve_command(data["verification"][0]["command"])
    task = project.create_task(data)["id"]
    project.ready(task)
    session = project.join("worker", ["code"])["session"]
    project.claim(task, session)
    (project.root / "agentic.config.json").write_text("{}")
    with pytest.raises(ControlError, match="Protected"):
        verify(project, task, session)
    (project.root / "agentic.config.json").unlink()
    project.release(task, session)
    data = contract()
    data["verification"][0]["inputs"] = list(data["scope"])
    next_task = project.create_task(data)["id"]
    project.ready(next_task)
    project.claim(next_task, session)
    project.checkpoint(next_task, session, checkpoint())
    verify(project, next_task, session)
    (project.root / "unrelated.py").write_text("changed = True\n")
    with pytest.raises(ControlError, match="outside task scope"):
        complete(project, next_task, session)


def test_human_canonical_constraints_are_bound_to_proof(project):
    node = project.knowledge.apply(
        [entity("retention")], project.store.knowledge_version, "contract"
    )["entities"][0]
    data = contract()
    data["requirements"] = [node["id"]]
    project.approve_command(data["verification"][0]["command"])
    task = project.create_task(data)["id"]
    project.ready(task)
    session = project.join("worker", ["code"])["session"]
    project.claim(task, session)
    project.checkpoint(task, session, checkpoint())
    verify(project, task, session)
    complete(project, task, session)
    project.knowledge.claim(
        {
            "subject": node["id"],
            "predicate": "days",
            "value": 30,
            "source_ref": "human decision",
            "authority": "human",
            "confidence": 1,
            "observation": "DECLARED",
        }
    )
    assert not proof_current(project, project.store.get(task))
    invalidate(project)
    assert project.store.get(task)["state"] == "NEEDS_REVALIDATION"


def test_running_verifier_retains_ownership_until_bounded_run_deadline(project):
    task, session = setup_task(project)
    started, finish = threading.Event(), threading.Event()
    outcomes = []

    def wait_for_release(*args, **kwargs):
        started.set()
        assert finish.wait(5)
        return GateResult(
            name="unit",
            command=["test"],
            required=True,
            exit_code=0,
            status="PASS",
            stdout="",
            stderr="",
            duration_seconds=0.1,
            metrics={},
            threshold_failures=[],
        )

    def execute():
        with Plane(project.root) as worker:
            outcomes.append(verify(worker, task, session))

    with patch("agentic_discipline.control.verification.run_gate", wait_for_release):
        thread = threading.Thread(target=execute)
        thread.start()
        try:
            assert started.wait(5)
            lease = next(item for item in project.store.list("lease") if item["state"] == "ACTIVE")
            with project.store.transaction():
                project.store.put(
                    "lease", {**lease, "expires_at": time.time() - 1}, expected=lease["version"]
                )
            other = project.join("next worker", ["code"])["session"]
            with pytest.raises(ControlError, match="not available"):
                project.claim(task, other)
            assert project.store.get(task)["active_run"]
        finally:
            finish.set()
            thread.join(5)
    assert not thread.is_alive() and outcomes[0]["evidence"][0]["result"] == "BLOCKED"
    assert project.store.get(task)["active_run"] is None


def test_repeated_symbols_rename_and_reconcile_keep_distinct_identities(project):
    path = project.root / "model.py"
    source = "class A:\n @property\n def value(self):\n  return 1\n @value.setter\n def value(self, new):\n  self._value = new\n"
    path.write_text(source)
    project.reconcile()
    before = {n["id"] for n in project.knowledge.query("A.value") if n["type"] == "symbol"}
    assert len(before) == 2
    path.write_text(source + "\n# comment\n")
    project.reconcile()
    assert {n["id"] for n in project.knowledge.query("A.value") if n["type"] == "symbol"} == before
    path.rename(project.root / "renamed.py")
    project.reconcile()
    assert {n["id"] for n in project.knowledge.query("A.value") if n["type"] == "symbol"} == before
    (project.root / "renamed.py").unlink()
    project.reconcile()
    assert not [n for n in project.knowledge.query("A.value") if n["type"] == "symbol"]
    assert all(project.store.get(i)["lifecycle"] == "HISTORICAL" for i in before)


def test_cli_failed_verification_is_nonzero_and_mcp_bad_input_is_recoverable(
    project, monkeypatch, capsys
):
    import sys

    task, session = setup_task(project)
    (project.root / "app.py").write_text("value = 2\n")
    incoming = project.root.parent / (project.root.name + "-request.json")
    incoming.write_text(json.dumps({"task_id": task, "session": session}))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "agentic",
            "--root",
            str(project.root),
            "api",
            "record_evidence",
            "--input",
            str(incoming),
            "--json",
        ],
    )
    with pytest.raises(SystemExit) as failure:
        cli.main()
    assert (
        failure.value.code == 1 and json.loads(capsys.readouterr().out)["data"]["status"] == "FAIL"
    )
    mcp = Session(project)
    mcp.initialized = mcp.ready = True
    node = project.knowledge.query()[0]
    bad = {
        "subject": node["id"],
        "predicate": "test",
        "value": True,
        "source_ref": "code",
        "authority": "inference",
        "confidence": 0.5,
        "observation": "INFERRED",
        "lifecycle": {},
    }
    result = mcp.receive(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "record_discovery", "arguments": {"data": bad}},
        }
    )
    assert result["result"]["isError"]
    assert mcp.receive({"jsonrpc": "2.0", "id": 2, "method": "ping"})["result"] == {}
    assert (
        mcp.receive({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": []}})[
            "error"
        ]["code"]
        == -32602
    )
    assert call(project, "doctor", {})["data"]["status"] == "FAIL"


def test_protected_symlinks_and_out_of_scope_links_cannot_be_added_after_verification(project):
    data = contract()
    data["verification"][0]["inputs"] = list(data["scope"])
    project.approve_command(data["verification"][0]["command"])
    task = project.create_task(data)["id"]
    project.ready(task)
    session = project.join("worker", ["code"])["session"]
    project.claim(task, session)
    project.checkpoint(task, session, checkpoint())
    verify(project, task, session)
    target = project.root.parent / (project.root.name + "-external.json")
    target.write_text("{}")
    protected = project.root / "agentic.config.json"
    protected.symlink_to(target)
    with pytest.raises(ControlError) as rejected:
        complete(project, task, session)
    assert rejected.value.code == "UNTRACKED_INPUT"
    protected.unlink()
    (project.root / "outside.json").symlink_to(target)
    with pytest.raises(ControlError) as rejected:
        complete(project, task, session)
    assert rejected.value.code == "SCOPE_EXCEEDED"


def test_conflicting_verified_claims_invalidate_parent_and_block_dependents(project):
    node = project.knowledge.apply(
        [entity("acceptance requirement")], project.store.knowledge_version, "contract"
    )["entities"][0]
    data = contract()
    data["requirements"] = [node["id"]]
    project.approve_command(data["verification"][0]["command"])
    task = project.create_task(data)["id"]
    project.ready(task)
    session = project.join("worker", ["code"])["session"]
    project.claim(task, session)
    project.checkpoint(task, session, checkpoint())
    evidence = verify(project, task, session)["evidence"][0]
    complete(project, task, session)
    for value in (True, False):
        project.knowledge.claim(
            {
                "subject": node["id"],
                "predicate": "interpretation",
                "value": value,
                "source_ref": "test_app.py",
                "authority": "verified",
                "confidence": 1,
                "observation": "VERIFIED",
                "evidence_refs": [evidence["id"]],
                "acceptance_index": 0,
            }
        )
    assert project.readiness(task)["status"] == "BLOCKED"
    assert not proof_current(project, project.store.get(task))
    invalidate(project)
    assert project.store.get(task)["state"] == "NEEDS_REVALIDATION"
    dependent = project.create_task({**data, "dependencies": [task]})["id"]
    assert project.readiness(dependent)["status"] == "BLOCKED"


def test_retry_budget_allows_initial_run_and_exact_number_of_retries(project):
    task, session = setup_task(project)
    (project.root / "app.py").write_text("value = 2\n")
    for attempt in range(1, 4):
        assert verify(project, task, session)["status"] == "FAIL"
        assert project.store.get(task)["attempts"] == attempt
    with pytest.raises(ControlError, match="Retry budget exhausted"):
        verify(project, task, session)
    assert len(project.store.list("evidence")) == 3


def test_changed_file_and_line_budgets_include_exact_boundary(project):
    data = contract()
    data["budget"].update(max_files=1, max_lines=2)
    project.approve_command(data["verification"][0]["command"])
    task = project.create_task(data)["id"]
    project.ready(task)
    session = project.join("worker", ["code"])["session"]
    project.claim(task, session)
    (project.root / "app.py").write_text("value = 1\n# second line\n")
    assert verify(project, task, session)["status"] == "PASS"
    (project.root / "app.py").write_text("value = 1\n# second line\n# third line\n")
    with pytest.raises(ControlError, match="line budget"):
        verify(project, task, session)


def test_primary_edit_after_merge_prevents_completion(tmp_path: Path):
    repository(tmp_path)
    with Plane(tmp_path) as plane:
        data = contract()
        plane.approve_command(data["verification"][0]["command"])
        task = plane.create_task(data)["id"]
        create_workspace(plane, task)
        plane.ready(task)
        session = plane.join("worker", ["code"])["session"]
        plane.claim(task, session)
        plane.checkpoint(task, session, checkpoint())
        verify(plane, task, session)
        merge_workspace(plane, task, session)
        (tmp_path / "app.py").write_text("value = 2\n")
        with pytest.raises(ControlError):
            complete(plane, task, session)
        assert plane.store.get(task)["state"] != "COMPLETED"


def test_protected_symlink_in_primary_after_merge_prevents_completion(tmp_path: Path):
    repository(tmp_path)
    with Plane(tmp_path) as plane:
        data = contract()
        data["verification"][0]["inputs"] = list(data["scope"])
        plane.approve_command(data["verification"][0]["command"])
        task = plane.create_task(data)["id"]
        create_workspace(plane, task)
        plane.ready(task)
        session = plane.join("worker", ["code"])["session"]
        plane.claim(task, session)
        plane.checkpoint(task, session, checkpoint())
        verify(plane, task, session)
        merge_workspace(plane, task, session)
        (tmp_path / "AGENTS.md").symlink_to(tmp_path / "app.py")
        with pytest.raises(ControlError):
            complete(plane, task, session)
        assert plane.store.get(task)["state"] != "COMPLETED"


def test_primary_protected_symlink_prevents_integration(tmp_path):
    repository(tmp_path)
    with Plane(tmp_path) as plane:
        data = contract()
        plane.approve_command(data["verification"][0]["command"])
        task = plane.create_task(data)["id"]
        create_workspace(plane, task)
        plane.ready(task)
        session = plane.join("worker", ["code"])["session"]
        plane.claim(task, session)
        plane.checkpoint(task, session, checkpoint())
        verify(plane, task, session)
        (tmp_path / "AGENTS.md").symlink_to(tmp_path / "app.py")
        with pytest.raises(ControlError):
            merge_workspace(plane, task, session)
        assert not plane.store.get(task).get("integration")


def test_scoped_fingerprint_matches_full_measurement_after_external_edits(tmp_path):
    from agentic_discipline.control.discovery import fingerprint

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("value = 1\n")
    (tmp_path / "src_extra").mkdir()
    (tmp_path / "src_extra" / "outside.py").write_text("outside = True\n")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "generated.py").write_text("generated = 1\n")
    (tmp_path / "src" / ".env").write_text("SECRET=excluded\n")
    (tmp_path / "src" / "linked.py").symlink_to(tmp_path / "src_extra" / "outside.py")
    scope = ["src", "build/generated.py", "missing.py"]
    before = fingerprint(tmp_path, scope)
    assert set(before) == {"src/app.py", "build/generated.py"}
    for value in (2, 3):
        (tmp_path / "src" / "app.py").write_text(f"value = {value}\n")
        full = fingerprint(tmp_path)
        scoped = fingerprint(tmp_path, scope)
        assert scoped == {name: full[name] for name in before}
        assert scoped["src/app.py"] != before["src/app.py"]
