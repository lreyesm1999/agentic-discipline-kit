"""Human blocker resolution and workspace root selection.

`resolve_blocker` records the owner's decision that unblocks a task, and
`workspace_root` decides which tree every verification and baseline of a task reads.
Existing tests reached them through full workflows, so a decision record could lose
its question, the owner could stop being the writer, or a merged or lost workspace
could send verification to the wrong tree unnoticed. Each case pins the exact
records or path.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from conftest import contract

from agentic_discipline.control.contracts import ControlError

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX symlinks")


def _force(project: Any, kind: str, identifier: str, **fields: Any) -> dict[str, Any]:
    with project.store.transaction():
        current = project.store.get(identifier, kind)
        return project.store.put(kind, {**current, **fields}, expected=current["version"])


def _task(project: Any, **fields: Any) -> dict[str, Any]:
    project.approve_command(contract()["verification"][0]["command"])
    task = project.create_task(contract())
    return _force(project, "task", task["id"], **fields) if fields else task


def _writer(project: Any, kind: str, record: dict[str, Any]) -> str:
    rows = project.store.db.execute(
        "SELECT actor, payload FROM events WHERE action = ?", (f"{kind}.write",)
    )
    (actor,) = [
        row["actor"]
        for row in rows
        if json.loads(row["payload"])["id"] == record["id"]
        and json.loads(row["payload"])["version"] == record["version"]
    ]
    return str(actor)


def _rejects(code: str, message: str, action: Any, *args: Any) -> None:
    with pytest.raises(ControlError) as caught:
        action(*args)
    assert (caught.value.code, str(caught.value)) == (code, message)


# --- resolve_blocker ------------------------------------------------------------------------


def test_resolving_a_blocker_records_the_owner_decision(project: Any) -> None:
    blocked = _task(project, state="BLOCKED", blocker="Choose a retention period")

    resolved = project.resolve_blocker(blocked["id"], "Keep thirty days")

    assert resolved == {**blocked, "version": blocked["version"] + 1, "blocker": None}
    assert project.store.get(blocked["id"], "task") == resolved
    (decision,) = project.store.list("decision")
    assert decision["id"].startswith("DECI-")
    assert decision == {
        "id": decision["id"],
        "version": 1,
        "task_id": blocked["id"],
        "question": "Choose a retention period",
        "decision": "Keep thirty days",
        "state": "DECIDED",
        "authority": "human",
    }
    assert _writer(project, "decision", decision) == "local-owner"
    assert _writer(project, "task", resolved) == "local-owner"


@pytest.mark.parametrize("decision", ["", "   "])
def test_a_decision_is_required(project: Any, decision: str) -> None:
    blocked = _task(project, state="BLOCKED", blocker="Question")
    _rejects(
        "DECISION_REQUIRED",
        "Record the decision that resolves the blocker",
        project.resolve_blocker,
        blocked["id"],
        decision,
    )
    assert project.store.list("decision") == []


@pytest.mark.parametrize(
    "fields",
    [{"state": "READY", "blocker": "Question"}, {"state": "BLOCKED", "blocker": None}, {}],
)
def test_only_tasks_blocked_by_a_human_question_can_be_resolved(
    project: Any, fields: dict[str, Any]
) -> None:
    task = _task(project, **fields)
    _rejects("NOT_BLOCKED", "Task has no human blocker", project.resolve_blocker, task["id"], "Yes")
    assert project.store.list("decision") == []
    assert project.store.get(task["id"], "task") == task


# --- workspace_root -------------------------------------------------------------------------


def _workspace(project: Any, path: Path, status: str = "ACTIVE") -> dict[str, Any]:
    with project.store.transaction():
        return project.store.put("workspace", {"path": str(path), "status": status})


def _worktree(project: Any, name: str = "TASK-1") -> Path:
    path = project.directory / "worktrees" / name
    path.mkdir(parents=True)
    return path


def test_tasks_without_a_workspace_use_the_repository(project: Any) -> None:
    assert project.workspace_root({"state": "CLAIMED"}) == project.root
    assert project.workspace_root({"state": "CLAIMED", "workspace_id": None}) == project.root


def test_an_active_workspace_is_used_while_it_exists(project: Any) -> None:
    path = _worktree(project)
    workspace = _workspace(project, path)
    for state in ("CLAIMED", "COMPLETED"):
        task = {"state": state, "workspace_id": workspace["id"], "integration": {"status": "PASS"}}
        assert project.workspace_root(task) == path


def test_completed_merged_work_reads_the_repository_without_its_workspace(project: Any) -> None:
    task = {
        "state": "COMPLETED",
        "workspace_id": "WORK-deleted",
        "integration": {"merge_performed": True},
    }
    assert project.workspace_root(task) == project.root


def test_a_removed_workspace_after_a_merge_reads_the_repository(project: Any) -> None:
    workspace = _workspace(project, project.directory / "worktrees" / "gone", "REMOVED")
    task = {
        "state": "VERIFYING",
        "workspace_id": workspace["id"],
        "integration": {"merge_performed": True},
    }
    assert project.workspace_root(task) == project.root


@pytest.mark.parametrize(
    "task_extra",
    [{}, {"integration": {"merge_performed": False}}, {"integration": {}}],
)
def test_a_removed_workspace_without_a_merge_is_lost(
    project: Any, task_extra: dict[str, Any]
) -> None:
    workspace = _workspace(project, project.directory / "worktrees" / "gone", "REMOVED")
    task = {"state": "CLAIMED", "workspace_id": workspace["id"], **task_extra}
    _rejects(
        "WORKSPACE_LOST",
        "Task workspace is missing; checkpoint retained",
        project.workspace_root,
        task,
    )


def test_workspaces_outside_the_managed_directory_or_not_directories_are_lost(
    project: Any, tmp_path: Path
) -> None:
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    nested = project.directory / "worktrees" / "a" / "b"
    nested.mkdir(parents=True)
    as_file = project.directory / "worktrees" / "file"
    as_file.write_text("x", encoding="utf-8")
    for path in (outside, nested, as_file, project.directory / "worktrees" / "missing"):
        workspace = _workspace(project, path)
        _rejects(
            "WORKSPACE_LOST",
            "Task workspace is missing; checkpoint retained",
            project.workspace_root,
            {"state": "CLAIMED", "workspace_id": workspace["id"]},
        )


@posix_only
def test_symlinked_workspaces_or_parents_are_lost(project: Any, tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    worktrees = project.directory / "worktrees"
    worktrees.mkdir(parents=True)
    linked = worktrees / "linked"
    linked.symlink_to(target, target_is_directory=True)
    workspace = _workspace(project, linked)
    _rejects(
        "WORKSPACE_LOST",
        "Task workspace is missing; checkpoint retained",
        project.workspace_root,
        {"state": "CLAIMED", "workspace_id": workspace["id"]},
    )

    real_parent = tmp_path / "real-worktrees"
    (real_parent / "TASK-2").mkdir(parents=True)
    linked.unlink()
    worktrees.rmdir()
    worktrees.symlink_to(real_parent, target_is_directory=True)
    workspace = _workspace(project, worktrees / "TASK-2")
    _rejects(
        "WORKSPACE_LOST",
        "Task workspace is missing; checkpoint retained",
        project.workspace_root,
        {"state": "CLAIMED", "workspace_id": workspace["id"]},
    )
