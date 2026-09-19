"""Isolated workspaces, record by record.

Worktrees carry the baseline every integration decision compares against, so a
workspace record with the wrong base, a refresh that keeps stale baselines or a
merge result missing its commit would let unreviewed contents reach the primary
repository. Existing tests followed the happy path by status fields. Each case
here compares the written records, events and git state whole.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from conftest import checkpoint, contract
from test_workspaces import repository

from agentic_discipline.common import run_git
from agentic_discipline.control import workspaces
from agentic_discipline.control.contracts import ControlError, digest
from agentic_discipline.control.discovery import fingerprint, git, line_counts, link_fingerprint
from agentic_discipline.control.plane import Plane
from agentic_discipline.control.verification import binding, verify
from agentic_discipline.control.workspaces import (
    cleanup,
    create_workspace,
    integration_gate,
    merge_workspace,
    refresh_workspace,
)


def _head(path: Path) -> str:
    return run_git(["rev-parse", "HEAD"], cwd=path).strip()


def _commit(path: Path, name: str, text: str) -> str:
    (path / name).write_text(text, encoding="utf-8")
    run_git(["add", name], cwd=path)
    run_git(["commit", "-m", f"edit {name}"], cwd=path)
    return _head(path)


def _events(plane: Any, action: str) -> list[dict[str, Any]]:
    rows = plane.store.db.execute(
        "SELECT actor, payload FROM events WHERE action = ? ORDER BY seq", (action,)
    )
    return [{"actor": r["actor"], "payload": json.loads(r["payload"])} for r in rows]


def _writer(plane: Any, kind: str, record: dict[str, Any]) -> str:
    (event,) = [
        e
        for e in _events(plane, f"{kind}.write")
        if e["payload"]["id"] == record["id"] and e["payload"]["version"] == record["version"]
    ]
    return str(event["actor"])


def _force(plane: Any, kind: str, identifier: str, **fields: Any) -> dict[str, Any]:
    with plane.store.transaction():
        current = plane.store.get(identifier, kind)
        return plane.store.put(kind, {**current, **fields}, expected=current["version"])


def _task(plane: Any, **changes: Any) -> str:
    data = {**contract(), **changes}
    plane.approve_command(data["verification"][0]["command"])
    return str(plane.create_task(data)["id"])


def _verified(plane: Any, **changes: Any) -> tuple[str, dict[str, Any], dict[str, Any], Path]:
    """A claimed task whose committed workspace change passed verification."""
    task = _task(plane, **changes)
    workspace = create_workspace(plane, task)
    plane.ready(task)
    agent = plane.join("worker", ["code", "terminal"])
    plane.claim(task, agent["session"])
    path = Path(workspace["path"])
    _commit(path, "app.py", "value = 1\n# integrated change\n")
    plane.checkpoint(task, agent["session"], checkpoint())
    verify(plane, task, agent["session"])
    return task, agent, workspace, path


# --- create_workspace ---------------------------------------------------------------------


def test_workspace_record_captures_the_committed_baseline(tmp_path: Path) -> None:
    repository(tmp_path)
    with Plane(tmp_path) as plane:
        task = _task(plane)
        planned = plane.store.get(task, "task")

        workspace = create_workspace(plane, task)

        directory = plane.directory / "worktrees" / task
        assert workspace["id"].startswith("WSP-")
        assert workspace == {
            "id": workspace["id"],
            "version": 1,
            "task_id": task,
            "path": str(directory),
            "branch": "agentic/" + task.lower(),
            "base_commit": _head(tmp_path),
            "baseline_files": fingerprint(tmp_path),
            "baseline_links": link_fingerprint(tmp_path),
            "status": "ACTIVE",
        }
        assert plane.store.get(workspace["id"], "workspace") == workspace
        assert plane.store.get(task, "task") == {
            **planned,
            "version": planned["version"] + 1,
            "workspace_id": workspace["id"],
        }
        branch = run_git(["branch", "--show-current"], cwd=directory).strip()
        assert (branch, _head(directory)) == (workspace["branch"], workspace["base_commit"])


def test_workspace_creation_removes_the_worktree_when_recording_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository(tmp_path)
    with Plane(tmp_path) as plane:
        task = _task(plane)
        planned = plane.store.get(task, "task")
        original = plane.store.put

        def failing(kind: str, data: dict[str, Any], **options: Any) -> dict[str, Any]:
            if kind == "workspace":
                raise ControlError("SIMULATED", "database write failed")
            return original(kind, data, **options)

        monkeypatch.setattr(plane.store, "put", failing)
        with pytest.raises(ControlError, match="database write failed"):
            create_workspace(plane, task)

        assert not (plane.directory / "worktrees" / task).exists()
        assert str(plane.directory / "worktrees" / task) not in run_git(
            ["worktree", "list"], cwd=tmp_path
        )
        assert plane.store.get(task, "task") == planned
        assert plane.store.list("workspace") == []


# --- integration_gate ---------------------------------------------------------------------


def test_integration_gate_records_its_result_as_the_owner(tmp_path: Path) -> None:
    repository(tmp_path)
    with Plane(tmp_path) as plane:
        # Other tasks exist before verification: approving their commands changes the policy.
        idle = [_task(plane), _task(plane)]
        task, agent, workspace, _ = _verified(plane)
        # Tasks that are not running cannot conflict semantically.
        for other, state in zip(idle, ("READY", "COMPLETED"), strict=True):
            _force(plane, "task", other, state=state)

        result = integration_gate(plane, task, agent["session"])

        stored = plane.store.get(task, "task")
        assert result == {
            "status": "PASS",
            "binding": digest(binding(plane, stored)),
            "target_commit": workspace["base_commit"],
            "merge_performed": False,
        }
        assert stored["integration"] == result
        assert _writer(plane, "task", stored) == agent["id"]


@pytest.mark.parametrize("state", ["CLAIMED", "RUNNING", "VERIFYING"])
def test_integration_gate_refuses_overlapping_running_work(tmp_path: Path, state: str) -> None:
    repository(tmp_path)
    with Plane(tmp_path) as plane:
        other = _task(plane)
        task, agent, _, _ = _verified(plane)
        _force(plane, "task", other, state=state)
        with pytest.raises(ControlError) as caught:
            integration_gate(plane, task, agent["session"])
        assert (caught.value.code, str(caught.value)) == (
            "SEMANTIC_CONFLICT",
            "Concurrent task needs serialization or explicit review",
        )


def test_integration_gate_allows_disjoint_running_work(tmp_path: Path) -> None:
    repository(tmp_path)
    with Plane(tmp_path) as plane:
        other = _task(plane, scope=["other.py"], boundaries=["other"])
        task, agent, _, _ = _verified(plane)
        _force(plane, "task", other, state="CLAIMED")
        assert integration_gate(plane, task, agent["session"])["status"] == "PASS"


# --- cleanup ------------------------------------------------------------------------------


def test_cleanup_removes_the_worktree_and_records_it(tmp_path: Path) -> None:
    repository(tmp_path)
    with Plane(tmp_path) as plane:
        task = _task(plane)
        workspace = create_workspace(plane, task)
        _force(plane, "task", task, state="CANCELLED")

        removed = cleanup(plane, task)

        assert removed == {**workspace, "version": 2, "status": "REMOVED"}
        assert plane.store.get(workspace["id"], "workspace") == removed
        assert not Path(workspace["path"]).exists()


# --- refresh_workspace --------------------------------------------------------------------


def test_refresh_rebases_and_renews_every_baseline(tmp_path: Path) -> None:
    repository(tmp_path)
    with Plane(tmp_path) as plane:
        task = _task(plane)
        workspace = create_workspace(plane, task)
        path = Path(workspace["path"])
        task_commit = _commit(path, "app.py", "value = 2\n")
        target = _commit(tmp_path, "other.py", "other = 1\n")
        before = _force(
            plane,
            "task",
            task,
            integration={"status": "PASS"},
            initial_files={"stale": "files"},
            initial_links={"stale": "links"},
            initial_line_counts={"stale": 1},
        )

        refreshed = refresh_workspace(plane, task)

        assert refreshed == {
            **workspace,
            "version": 2,
            "base_commit": target,
            "baseline_files": fingerprint(tmp_path),
            "baseline_links": link_fingerprint(tmp_path),
        }
        assert plane.store.get(task, "task") == {
            **before,
            "version": before["version"] + 1,
            "integration": None,
            "initial_files": fingerprint(tmp_path),
            "initial_links": link_fingerprint(tmp_path),
            "initial_line_counts": line_counts(tmp_path, list(fingerprint(tmp_path))),
        }
        run_git(["merge-base", "--is-ancestor", target, "HEAD"], cwd=path)
        assert _head(path) != task_commit
        assert (path / "other.py").read_text(encoding="utf-8") == "other = 1\n"
        assert (path / "app.py").read_text(encoding="utf-8") == "value = 2\n"


def test_a_conflicting_refresh_aborts_its_rebase(tmp_path: Path) -> None:
    repository(tmp_path)
    with Plane(tmp_path) as plane:
        task = _task(plane)
        path = Path(create_workspace(plane, task)["path"])
        task_commit = _commit(path, "app.py", "value = 2\n")
        _commit(tmp_path, "app.py", "value = 3\n")

        with pytest.raises(RuntimeError):
            refresh_workspace(plane, task)

        assert git(path, ["rev-parse", "--verify", "REBASE_HEAD"]) == ""
        assert _head(path) == task_commit


def test_a_rebase_that_never_started_is_reported_not_aborted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agentic_discipline.control import workspaces

    repository(tmp_path)
    with Plane(tmp_path) as plane:
        task = _task(plane)
        create_workspace(plane, task)
        calls: list[list[str]] = []

        def refusing(args: list[str], cwd: Path) -> str:
            calls.append(args)
            raise RuntimeError("rebase refused to start")

        monkeypatch.setattr(workspaces, "run_git", refusing)
        with pytest.raises(RuntimeError) as caught:
            refresh_workspace(plane, task)

        assert str(caught.value) == "rebase refused to start"
        assert [args[:2] for args in calls] == [["rebase", _head(tmp_path)]]


# --- merge_workspace ----------------------------------------------------------------------


def test_merge_fast_forwards_and_records_the_merged_commit(tmp_path: Path) -> None:
    repository(tmp_path)
    with Plane(tmp_path) as plane:
        task, agent, _, path = _verified(plane)
        target = _head(path)

        result = merge_workspace(plane, task, agent["session"])

        stored = plane.store.get(task, "task")
        assert result == {
            "status": "PASS",
            "binding": digest(binding(plane, stored)),
            "target_commit": stored["integration"]["target_commit"],
            "merge_performed": True,
            "merged_commit": target,
            "merged_files": fingerprint(tmp_path),
        }
        assert stored["integration"] == result
        assert _writer(plane, "task", stored) == agent["id"]
        assert _events(plane, "workspace.merged") == [
            {"actor": agent["id"], "payload": {"task_id": task, "commit": target}}
        ]
        assert _head(tmp_path) == target


def test_merge_recovery_records_the_reviewed_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository(tmp_path)
    with Plane(tmp_path) as plane:
        task, agent, _, path = _verified(plane)
        target = _head(path)
        original = plane.store.put

        def interrupted(kind: str, data: dict[str, Any], **options: Any) -> dict[str, Any]:
            if kind == "task" and (data.get("integration") or {}).get("merge_performed"):
                raise RuntimeError("simulated commit interruption")
            return original(kind, data, **options)

        with monkeypatch.context() as context:
            context.setattr(plane.store, "put", interrupted)
            with pytest.raises(RuntimeError, match="commit interruption"):
                merge_workspace(plane, task, agent["session"])
        gated = plane.store.get(task, "task")["integration"]

        result = merge_workspace(plane, task, agent["session"])

        stored = plane.store.get(task, "task")
        assert result == {
            **gated,
            "merge_performed": True,
            "merged_commit": target,
            "merged_files": fingerprint(tmp_path),
            "recovered": True,
        }
        assert stored["integration"] == result
        assert _writer(plane, "task", stored) == agent["id"]
        assert _events(plane, "workspace.merge_recovered") == [
            {"actor": agent["id"], "payload": {"task_id": task, "commit": target}}
        ]
        assert _events(plane, "workspace.merged") == []


def test_merge_recovery_refuses_contents_that_were_never_gated(tmp_path: Path) -> None:
    repository(tmp_path)
    with Plane(tmp_path) as plane:
        task, agent, workspace, _ = _verified(plane)
        # Someone merged the branch by hand, so no integration result was ever recorded.
        run_git(["merge", "--ff-only", "--", workspace["branch"]], cwd=tmp_path)
        before = plane.store.get(task, "task")

        with pytest.raises(ControlError) as caught:
            merge_workspace(plane, task, agent["session"])

        assert (caught.value.code, str(caught.value)) == (
            "INTEGRATION_MISMATCH",
            "Cannot recover a merge whose reviewed contents changed",
        )
        assert plane.store.get(task, "task") == before


def test_merge_recovery_refuses_a_task_changed_meanwhile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository(tmp_path)
    with Plane(tmp_path) as plane:
        task, agent, _, _ = _verified(plane)
        original_put = plane.store.put

        def interrupted(kind: str, data: dict[str, Any], **options: Any) -> dict[str, Any]:
            if kind == "task" and (data.get("integration") or {}).get("merge_performed"):
                raise RuntimeError("simulated commit interruption")
            return original_put(kind, data, **options)

        with monkeypatch.context() as context:
            context.setattr(plane.store, "put", interrupted)
            with pytest.raises(RuntimeError, match="commit interruption"):
                merge_workspace(plane, task, agent["session"])

        original_proof = workspaces.completion_proof

        def racing(current_plane: Any, current_task: dict[str, Any]) -> Any:
            proof = original_proof(current_plane, current_task)
            _force(plane, "task", task, note="changed meanwhile")
            return proof

        monkeypatch.setattr(workspaces, "completion_proof", racing)
        with pytest.raises(ControlError) as caught:
            merge_workspace(plane, task, agent["session"])

        assert (caught.value.code, str(caught.value)) == (
            "VERSION_CONFLICT",
            "Task changed during merge recovery",
        )
        assert not (plane.store.get(task, "task")["integration"] or {}).get("merge_performed")


# --- finished work and concurrent changes -------------------------------------------------


def _change_task_during(
    monkeypatch: pytest.MonkeyPatch, plane: Any, task: str, command: tuple[str, ...]
) -> None:
    original = workspaces.run_git

    def racing(arguments: list[str], *rest: Any, **options: Any) -> Any:
        output = original(arguments, *rest, **options)
        if tuple(arguments[: len(command)]) == command:
            _force(plane, "task", task, note="changed meanwhile")
        return output

    monkeypatch.setattr(workspaces, "run_git", racing)


@pytest.mark.parametrize("state", ["COMPLETED", "CANCELLED", "SUPERSEDED"])
def test_cleanup_accepts_every_finished_state(tmp_path: Path, state: str) -> None:
    repository(tmp_path)
    with Plane(tmp_path) as plane:
        task = _task(plane)
        workspace = create_workspace(plane, task)
        _force(plane, "task", task, state=state)
        assert cleanup(plane, task) == {**workspace, "version": 2, "status": "REMOVED"}


@pytest.mark.parametrize("state", ["COMPLETED", "CANCELLED", "SUPERSEDED"])
def test_refresh_refuses_finished_work(tmp_path: Path, state: str) -> None:
    repository(tmp_path)
    with Plane(tmp_path) as plane:
        task = _task(plane)
        workspace = create_workspace(plane, task)
        _force(plane, "task", task, state=state)
        with pytest.raises(ControlError) as caught:
            refresh_workspace(plane, task)
        assert (caught.value.code, str(caught.value)) == (
            "WORKSPACE_BUSY",
            "An idle isolated workspace is required",
        )
        assert plane.store.get(workspace["id"], "workspace") == workspace


def test_workspace_creation_refuses_a_task_changed_meanwhile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository(tmp_path)
    with Plane(tmp_path) as plane:
        task = _task(plane)
        _change_task_during(monkeypatch, plane, task, ("worktree", "add"))

        with pytest.raises(ControlError) as caught:
            create_workspace(plane, task)

        assert (caught.value.code, str(caught.value)) == (
            "VERSION_CONFLICT",
            "Task changed during workspace creation",
        )
        assert not (plane.directory / "worktrees" / task).exists()
        assert plane.store.list("workspace") == []


def test_refresh_refuses_a_task_changed_meanwhile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository(tmp_path)
    with Plane(tmp_path) as plane:
        task = _task(plane)
        workspace = create_workspace(plane, task)
        _commit(tmp_path, "other.py", "other = 1\n")
        _change_task_during(monkeypatch, plane, task, ("rebase",))

        with pytest.raises(ControlError) as caught:
            refresh_workspace(plane, task)

        assert (caught.value.code, str(caught.value)) == (
            "VERSION_CONFLICT",
            "Task changed while refreshing; reconcile workspace",
        )
        assert plane.store.get(workspace["id"], "workspace") == workspace


posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX symlinks")


@posix_only
def test_workspace_parent_must_not_be_a_symlink(tmp_path: Path) -> None:
    repository(tmp_path)
    with Plane(tmp_path) as plane:
        task = _task(plane)
        elsewhere = tmp_path.parent / (tmp_path.name + "-worktrees")
        elsewhere.mkdir()
        (plane.directory / "worktrees").symlink_to(elsewhere, target_is_directory=True)

        with pytest.raises(ControlError) as caught:
            create_workspace(plane, task)

        assert (caught.value.code, str(caught.value)) == (
            "INVALID_PATH",
            "Workspace parent cannot be a symlink",
        )
        assert list(elsewhere.iterdir()) == []


@posix_only
def test_symlink_baselines_are_kept_through_integration_and_merge(tmp_path: Path) -> None:
    repository(tmp_path)
    (tmp_path / "current").symlink_to("app.py")
    run_git(["add", "current"], cwd=tmp_path)
    run_git(["commit", "-m", "link"], cwd=tmp_path)
    with Plane(tmp_path) as plane:
        # Verifiers refuse symlinks among their inputs, so measure only the task files.
        (unit,) = contract()["verification"]
        task, agent, workspace, _ = _verified(
            plane, verification=[{**unit, "inputs": ["app.py", "test_app.py"]}]
        )
        assert workspace["baseline_links"] == link_fingerprint(tmp_path) != {}

        assert integration_gate(plane, task, agent["session"])["status"] == "PASS"
        assert merge_workspace(plane, task, agent["session"])["merge_performed"] is True
