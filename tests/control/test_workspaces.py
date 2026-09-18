from pathlib import Path

import pytest
from conftest import checkpoint, contract

from agentic_discipline.common import run_git
from agentic_discipline.control.contracts import ControlError
from agentic_discipline.control.plane import Plane, adopt
from agentic_discipline.control.verification import complete, verify
from agentic_discipline.control.workspaces import (
    cleanup,
    create_workspace,
    integration_gate,
    merge_workspace,
    parallel_safety,
    refresh_workspace,
)


def repository(root):
    (root / "app.py").write_text("value = 1\n")
    (root / "test_app.py").write_text("import app\nassert app.value == 1\n")
    (root / ".gitignore").write_text(".agentic/\n__pycache__/\n")
    run_git(["init"], cwd=root)
    run_git(["config", "user.name", "Control Test"], cwd=root)
    run_git(["config", "user.email", "test@example.invalid"], cwd=root)
    run_git(["add", "."], cwd=root)
    run_git(["commit", "-m", "baseline"], cwd=root)
    adopt(root)


def test_worktree_verify_integration_merge_and_cleanup(tmp_path: Path):
    repository(tmp_path)
    with Plane(tmp_path) as plane:
        data = contract()
        plane.approve_command(data["verification"][0]["command"])
        task = plane.create_task(data)
        workspace = create_workspace(plane, task["id"])
        assert Path(workspace["path"]).is_dir()
        with pytest.raises(ControlError):
            create_workspace(plane, task["id"])
        refresh_workspace(plane, task["id"])
        plane.ready(task["id"])
        worker = plane.join("isolated", ["code", "terminal"])
        plane.claim(task["id"], worker["session"])
        path = Path(workspace["path"])
        (path / "app.py").write_text("value = 1\n# reviewed change\n")
        assert "reviewed" not in (tmp_path / "app.py").read_text()
        plane.checkpoint(task["id"], worker["session"], checkpoint())
        assert verify(plane, task["id"], worker["session"])["status"] == "PASS"
        assert integration_gate(plane, task["id"], worker["session"])["status"] == "PASS"
        with pytest.raises(ControlError):
            complete(plane, task["id"], worker["session"])
        with pytest.raises(ControlError, match="Commit verified"):
            merge_workspace(plane, task["id"], worker["session"])
        run_git(["add", "app.py"], cwd=path)
        run_git(["commit", "-m", "verified task"], cwd=path)
        assert merge_workspace(plane, task["id"], worker["session"])["merge_performed"]
        assert "reviewed" in (tmp_path / "app.py").read_text()
        assert complete(plane, task["id"], worker["session"])["state"] == "COMPLETED"
        assert cleanup(plane, task["id"])["status"] == "REMOVED"
        assert not path.exists()
        assert plane.workspace_root(plane.store.get(task["id"])) == tmp_path


def test_parallel_classification_and_lost_workspace(tmp_path: Path):
    a = contract()
    assert parallel_safety(a, a)["status"] == "CONFLICTING"
    b = {**a, "scope": ["other.py"]}
    assert parallel_safety(a, b)["status"] == "SERIALIZE"
    b["boundaries"] = ["different boundary"]
    assert parallel_safety(a, b)["status"] == "SAFE_PARALLEL"
    b["risk"] = "HIGH"
    assert parallel_safety(a, b)["status"] == "PARALLEL_WITH_REVIEW"
    repository(tmp_path)
    with Plane(tmp_path) as plane:
        task = plane.create_task(a)
        workspace = create_workspace(plane, task["id"])
        with pytest.raises(ControlError):
            cleanup(plane, task["id"])
        run_git(["worktree", "remove", workspace["path"]], cwd=tmp_path)
        with pytest.raises(ControlError, match="missing"):
            plane.workspace_root(plane.store.get(task["id"]))


def test_two_agents_parallel_then_refresh_verify_and_integrate(tmp_path: Path):
    import sys

    from agentic_discipline.control.verification import proof_current

    repository(tmp_path)
    (tmp_path / "left.py").write_text("value = 1\n")
    (tmp_path / "right.py").write_text("value = 1\n")
    run_git(["add", "."], cwd=tmp_path)
    run_git(["commit", "-m", "independent modules"], cwd=tmp_path)
    with Plane(tmp_path) as plane:
        work = []
        for name in ("left", "right"):
            data = contract()
            data["scope"] = [name + ".py"]
            data["boundaries"] = [name]
            data["verification"][0].update(
                command=[sys.executable, "-B", "-c", f"import {name}; assert {name}.value == 2"],
                inputs=[name + ".py"],
            )
            plane.approve_command(data["verification"][0]["command"])
            task = plane.create_task(data)["id"]
            workspace = create_workspace(plane, task)
            plane.ready(task)
            session = plane.join(name, ["code", "terminal"])["session"]
            plane.claim(task, session)
            work.append((name, task, session, Path(workspace["path"])))
        assert len([item for item in plane.store.list("lease") if item["state"] == "ACTIVE"]) == 2
        for name, task, session, path in work:
            (path / (name + ".py")).write_text("value = 2\n")
            run_git(["add", name + ".py"], cwd=path)
            run_git(["commit", "-m", "implement " + name], cwd=path)
            plane.checkpoint(task, session, checkpoint())
            assert verify(plane, task, session)["status"] == "PASS"
        _, task, session, _ = work[0]
        merge_workspace(plane, task, session)
        complete(plane, task, session)
        cleanup(plane, task)
        _, task, session, _ = work[1]
        with pytest.raises(ControlError, match="Refresh/rebase"):
            integration_gate(plane, task, session)
        refresh_workspace(plane, task)
        assert verify(plane, task, session)["status"] == "PASS"
        merge_workspace(plane, task, session)
        complete(plane, task, session)
        cleanup(plane, task)
        assert all(proof_current(plane, plane.store.get(t)) for _, t, _, _ in work)
        assert all((tmp_path / (n + ".py")).read_text() == "value = 2\n" for n, _, _, _ in work)


def test_refresh_conflict_aborts_rebase_and_preserves_commits(tmp_path: Path):
    repository(tmp_path)
    with Plane(tmp_path) as plane:
        task = plane.create_task(contract())["id"]
        workspace = create_workspace(plane, task)
        path = Path(workspace["path"])
        (path / "app.py").write_text("value = 2\n")
        run_git(["add", "app.py"], cwd=path)
        run_git(["commit", "-m", "task edit"], cwd=path)
        head = run_git(["rev-parse", "HEAD"], cwd=path).strip()
        (tmp_path / "app.py").write_text("value = 3\n")
        run_git(["add", "app.py"], cwd=tmp_path)
        run_git(["commit", "-m", "external edit"], cwd=tmp_path)
        with pytest.raises(RuntimeError):
            refresh_workspace(plane, task)
        assert run_git(["rev-parse", "HEAD"], cwd=path).strip() == head
        assert not run_git(["status", "--porcelain"], cwd=path).strip()
        assert (path / "app.py").read_text() == "value = 2\n"


def test_merge_recovers_when_git_succeeds_before_database_failure(tmp_path: Path, monkeypatch):
    repository(tmp_path)
    with Plane(tmp_path) as plane:
        data = contract()
        plane.approve_command(data["verification"][0]["command"])
        task = plane.create_task(data)["id"]
        workspace = create_workspace(plane, task)
        plane.ready(task)
        session = plane.join("worker", ["code"])["session"]
        plane.claim(task, session)
        path = Path(workspace["path"])
        (path / "app.py").write_text("value = 1\n# integrated change\n")
        run_git(["add", "app.py"], cwd=path)
        run_git(["commit", "-m", "task"], cwd=path)
        plane.checkpoint(task, session, checkpoint())
        verify(plane, task, session)
        original = plane.store.put

        def interrupted(kind, payload, **kwargs):
            if kind == "task" and (payload.get("integration") or {}).get("merge_performed"):
                raise RuntimeError("simulated commit interruption")
            return original(kind, payload, **kwargs)

        with monkeypatch.context() as context:
            context.setattr(plane.store, "put", interrupted)
            with pytest.raises(RuntimeError, match="commit interruption"):
                merge_workspace(plane, task, session)
        assert "integrated change" in (tmp_path / "app.py").read_text()
        assert plane.store.get(task)["state"] == "VERIFYING"
        assert merge_workspace(plane, task, session)["recovered"]
        assert complete(plane, task, session)["state"] == "COMPLETED"
