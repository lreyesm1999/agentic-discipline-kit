"""Verification, completion and workspace rules asserted by exact code and message.

These refusals decide whether work may be verified, completed or integrated, and
agents branch on their codes. Each case breaks one rule on an otherwise valid task
and asserts the exact outcome, together with the boundary the rule must accept.
Workspace cases run against a real Git repository.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest
from conftest import checkpoint, contract
from test_workspaces import repository

from agentic_discipline.common import run_git
from agentic_discipline.control import workspaces
from agentic_discipline.control.contracts import ControlError
from agentic_discipline.control.plane import Plane
from agentic_discipline.control.verification import complete, verify
from agentic_discipline.control.workspaces import (
    cleanup,
    create_workspace,
    integration_gate,
    merge_workspace,
    refresh_workspace,
)


def _rejects(code: str, message: str, action: Any, *args: Any) -> None:
    with pytest.raises(ControlError) as caught:
        action(*args)
    assert (caught.value.code, str(caught.value)) == (code, message)


def _force(plane: Any, kind: str, identifier: str, **fields: Any) -> dict[str, Any]:
    """Put a record into a state that is expensive to reach through the workflow."""
    with plane.store.transaction():
        current = plane.store.get(identifier, kind)
        return plane.store.put(kind, {**current, **fields}, expected=current["version"])


def _claimed(plane: Any, **changes: Any) -> tuple[str, str]:
    data = {**contract(), **changes}
    plane.approve_command(data["verification"][0]["command"])
    task = plane.create_task(data)["id"]
    plane.ready(task)
    session = plane.join("worker", ["code", "terminal"])["session"]
    plane.claim(task, session)
    return task, session


def _verified(plane: Any, with_checkpoint: bool = True) -> tuple[str, str]:
    task, session = _claimed(plane)
    if with_checkpoint:
        plane.checkpoint(task, session, checkpoint())
    assert verify(plane, task, session)["status"] == "PASS"
    return task, session


# --- check_changes, through verify --------------------------------------------------------


def test_changed_file_budget_allows_its_limit_and_rejects_one_more(project: Any) -> None:
    task, session = _claimed(project)  # max_files is 2
    (project.root / "app.py").write_text("value = 1\n# reviewed\n")
    (project.root / "test_app.py").write_text("import app\nassert app.value == 1\n# reviewed\n")
    assert verify(project, task, session)["status"] == "PASS"


def test_changed_file_budget_is_exceeded(project: Any) -> None:
    task, session = _claimed(project, budget={**contract()["budget"], "max_files": 1})
    (project.root / "app.py").write_text("value = 1\n# reviewed\n")
    (project.root / "test_app.py").write_text("import app\nassert app.value == 1\n# reviewed\n")
    _rejects("BUDGET_EXCEEDED", "Changed-file budget exceeded", verify, project, task, session)


def test_changes_outside_scope_are_rejected(project: Any) -> None:
    task, session = _claimed(project)
    (project.root / "other.py").write_text("x = 1\n")
    _rejects("SCOPE_EXCEEDED", "Changes outside task scope", verify, project, task, session)


def test_protected_changes_need_review(project: Any) -> None:
    # A protected path a task contract may name (unlike .agentic or .git metadata).
    protected = "agentic.config.json"
    assert protected in project.policy()["protected_paths"]
    task, session = _claimed(project, scope=["app.py", "test_app.py", protected])
    (project.root / protected).write_text("{}\n")
    _rejects("PROTECTED_CHANGE", "Protected changes require review", verify, project, task, session)


@pytest.mark.parametrize(("lines", "allowed"), [(100, True), (101, False)])
def test_changed_line_budget_boundary(project: Any, lines: int, allowed: bool) -> None:
    task, session = _claimed(project)  # max_lines is 100
    (project.root / "app.py").write_text("value = 1\n" + "# padding\n" * (lines - 1))
    if allowed:
        assert verify(project, task, session)["status"] == "PASS"
    else:
        _rejects(
            "BUDGET_EXCEEDED",
            "Conservative changed-file line budget exceeded",
            verify,
            project,
            task,
            session,
        )


# --- verify -------------------------------------------------------------------------------


@pytest.mark.parametrize("state", ["CLAIMED", "RUNNING", "VERIFYING", "FAILED"])
def test_verify_accepts_every_owned_working_state(project: Any, state: str) -> None:
    task, session = _claimed(project)
    _force(project, "task", task, state=state)
    assert verify(project, task, session)["status"] == "PASS"


def test_verify_rejects_a_task_that_is_not_being_worked_on(project: Any) -> None:
    task, session = _claimed(project)
    _force(project, "task", task, state="READY")
    _rejects(
        "INVALID_TRANSITION",
        "Task cannot be verified in this state",
        verify,
        project,
        task,
        session,
    )


def test_verify_requires_no_readiness_blockers(project: Any) -> None:
    task, session = _claimed(project)
    _force(project, "task", task, blocker="Choose a retention period")
    _rejects("NOT_READY", "Readiness blockers prevent verification", verify, project, task, session)


def test_retry_budget_allows_its_limit_and_rejects_one_more(project: Any) -> None:
    task, session = _claimed(project)  # max_retries is 2
    _force(project, "task", task, attempts=2)
    assert verify(project, task, session)["status"] == "PASS"
    _force(project, "task", task, attempts=3)
    _rejects(
        "BUDGET_EXCEEDED",
        "Retry budget exhausted; checkpoint and review",
        verify,
        project,
        task,
        session,
    )


def test_verify_refuses_to_start_a_second_run(project: Any) -> None:
    task, session = _claimed(project)
    _force(project, "task", task, active_run="RUN-1")
    _rejects("VERIFICATION_BUSY", "A verifier is already running", verify, project, task, session)


def test_verify_stops_when_the_runtime_budget_is_spent(project: Any) -> None:
    task, session = _claimed(project)  # max_runtime is 30
    _force(project, "task", task, runtime_used=30)
    _rejects("BUDGET_EXCEEDED", "Runtime budget exhausted", verify, project, task, session)
    assert project.store.get(task, "task")["state"] == "FAILED"


# --- complete and completion_proof --------------------------------------------------------


def test_only_a_verified_task_can_complete(project: Any) -> None:
    task, session = _claimed(project)
    _rejects(
        "INVALID_TRANSITION", "Only a verified task can complete", complete, project, task, session
    )


def test_verified_task_with_an_intact_checkpoint_completes(project: Any) -> None:
    task, session = _verified(project)
    completed = complete(project, task, session)
    assert completed["state"] == "COMPLETED"
    assert completed["proof"]


def test_completion_requires_no_readiness_blockers(project: Any) -> None:
    task, session = _verified(project)
    _force(project, "task", task, blocker="Choose a retention period")
    _rejects(
        "NOT_READY",
        "Dependencies, knowledge, permissions or decisions are blocked",
        complete,
        project,
        task,
        session,
    )


def test_completion_requires_an_execution_of_every_verifier(project: Any) -> None:
    task, session = _claimed(project)
    _force(project, "task", task, state="VERIFYING")
    _rejects(
        "MISSING_EVIDENCE", "Required verifier has no execution", complete, project, task, session
    )


def test_completion_rejects_stale_proof(project: Any) -> None:
    task, session = _verified(project)
    (project.root / "app.py").write_text("value = 1\n# edited after verification\n")
    _rejects(
        "STALE_OR_FAILED_EVIDENCE",
        "Latest required proof is stale, failed or tampered",
        complete,
        project,
        task,
        session,
    )


def test_completion_requires_a_checkpoint(project: Any) -> None:
    task, session = _verified(project, with_checkpoint=False)
    _rejects(
        "CHECKPOINT_REQUIRED", "Checkpoint before completion", complete, project, task, session
    )


def test_completion_rejects_a_tampered_checkpoint(project: Any) -> None:
    task, session = _verified(project)
    (saved,) = [c for c in project.store.list("checkpoint") if c["task_id"] == task]
    _force(
        project,
        "checkpoint",
        saved["id"],
        payload={**saved["payload"], "next_action": "Skip review"},
    )
    _rejects(
        "CHECKPOINT_CORRUPT",
        "Checkpoint content does not match its hash",
        complete,
        project,
        task,
        session,
    )


# --- workspaces ---------------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path: Path) -> Any:
    repository(tmp_path)
    with Plane(tmp_path) as plane:
        yield plane


def _task(plane: Any) -> str:
    data = contract()
    plane.approve_command(data["verification"][0]["command"])
    return plane.create_task(data)["id"]


@pytest.mark.parametrize("state", ["PLANNED", "READY"])
def test_workspace_is_allocated_before_claiming(repo: Any, state: str) -> None:
    task = _task(repo)
    if state == "READY":
        repo.ready(task)
    assert Path(create_workspace(repo, task)["path"]).is_dir()
    _rejects("WORKSPACE_EXISTS", "Task already has a workspace", create_workspace, repo, task)


def test_workspace_cannot_be_allocated_after_claiming(repo: Any) -> None:
    task = _task(repo)
    repo.ready(task)
    repo.claim(task, repo.join("worker", ["code", "terminal"])["session"])
    _rejects(
        "INVALID_TRANSITION", "Allocate isolation before claiming", create_workspace, repo, task
    )


def test_workspace_requires_a_committed_baseline(repo: Any) -> None:
    task = _task(repo)
    (repo.root / "app.py").write_text("value = 1\n# uncommitted\n")
    _rejects(
        "DIRTY_BASELINE",
        "Commit the reviewed baseline before creating worktrees",
        create_workspace,
        repo,
        task,
    )


def test_cleanup_preserves_active_workspaces_and_removes_finished_ones(repo: Any) -> None:
    active = _task(repo)
    create_workspace(repo, active)
    message = "Preserve workspace for active work"
    _rejects("WORKSPACE_BUSY", message, cleanup, repo, active)

    without_workspace = _task(repo)
    repo.transition(without_workspace, "CANCELLED", "not needed")
    _rejects("WORKSPACE_BUSY", message, cleanup, repo, without_workspace)

    repo.transition(active, "CANCELLED", "scope removed")
    assert cleanup(repo, active)["status"] == "REMOVED"


def test_cleanup_refuses_unmanaged_workspace_paths(repo: Any, tmp_path: Path) -> None:
    task = _task(repo)
    workspace = create_workspace(repo, task)
    repo.transition(task, "CANCELLED", "scope removed")
    _force(repo, "workspace", workspace["id"], path=str(tmp_path / "elsewhere"))
    _rejects("INVALID_PATH", "Unmanaged workspace", cleanup, repo, task)


def test_refresh_requires_an_idle_isolated_workspace(repo: Any) -> None:
    message = "An idle isolated workspace is required"
    plain = _task(repo)
    _rejects("WORKSPACE_BUSY", message, refresh_workspace, repo, plain)

    busy = _task(repo)
    create_workspace(repo, busy)
    _force(repo, "task", busy, active_run="RUN-1")
    _rejects("WORKSPACE_BUSY", message, refresh_workspace, repo, busy)

    finished = _task(repo)
    create_workspace(repo, finished)
    repo.transition(finished, "CANCELLED", "scope removed")
    _rejects("WORKSPACE_BUSY", message, refresh_workspace, repo, finished)


def test_refresh_requires_clean_workspace_and_baseline(repo: Any) -> None:
    task = _task(repo)
    workspace = Path(create_workspace(repo, task)["path"])
    (workspace / "app.py").write_text("value = 1\n# local edit\n")
    _rejects(
        "DIRTY_WORKSPACE",
        "Commit or checkpoint local edits before refreshing",
        refresh_workspace,
        repo,
        task,
    )
    run_git(["checkout", "--", "app.py"], cwd=workspace)
    (repo.root / "app.py").write_text("value = 1\n# primary edit\n")
    _rejects("DIRTY_BASELINE", "Primary baseline must be committed", refresh_workspace, repo, task)

    run_git(["checkout", "--", "app.py"], cwd=repo.root)
    head = run_git(["rev-parse", "HEAD"], cwd=repo.root).strip()
    assert refresh_workspace(repo, task)["base_commit"] == head


def _claimed_workspace(plane: Any) -> tuple[str, str, Path]:
    task = _task(plane)
    path = Path(create_workspace(plane, task)["path"])
    plane.ready(task)
    session = plane.join("isolated", ["code", "terminal"])["session"]
    plane.claim(task, session)
    return task, session, path


def test_integration_and_merge_need_an_isolated_workspace(repo: Any) -> None:
    task = _task(repo)
    repo.ready(task)
    session = repo.join("worker", ["code", "terminal"])["session"]
    repo.claim(task, session)
    message = "Task uses the primary repository"
    _rejects("NO_WORKSPACE", message, integration_gate, repo, task, session)
    _rejects("NO_WORKSPACE", message, merge_workspace, repo, task, session)


def test_integration_rejects_a_moved_primary_commit(repo: Any) -> None:
    task, session, _ = _claimed_workspace(repo)
    (repo.root / "README.md").write_text("# moved\n")
    run_git(["add", "README.md"], cwd=repo.root)
    run_git(["commit", "-m", "primary moved"], cwd=repo.root)
    _rejects(
        "BASELINE_CHANGED",
        "Refresh/rebase the workspace before integration",
        integration_gate,
        repo,
        task,
        session,
    )


def test_integration_rejects_uncommitted_primary_changes(repo: Any) -> None:
    task, session, _ = _claimed_workspace(repo)
    (repo.root / "notes.txt").write_text("edited outside the task\n")
    _rejects(
        "BASELINE_CHANGED",
        "Primary workspace changed outside the task",
        integration_gate,
        repo,
        task,
        session,
    )


def test_merge_requires_committed_verified_changes(repo: Any) -> None:
    task, session, path = _claimed_workspace(repo)
    (path / "app.py").write_text("value = 1\n# reviewed change\n")
    repo.checkpoint(task, session, checkpoint())
    assert verify(repo, task, session)["status"] == "PASS"
    _rejects(
        "DIRTY_WORKSPACE",
        "Commit verified changes before merging",
        merge_workspace,
        repo,
        task,
        session,
    )

    # The gate passed but nothing was merged, so completion is still refused.
    _rejects(
        "INTEGRATION_REQUIRED",
        "Workspace changes need a current integration gate",
        complete,
        repo,
        task,
        session,
    )
    run_git(["add", "app.py"], cwd=path)
    run_git(["commit", "-m", "verified task"], cwd=path)
    assert merge_workspace(repo, task, session)["merge_performed"]
    assert complete(repo, task, session)["state"] == "COMPLETED"


def _verified_workspace(plane: Any) -> tuple[str, str, Path]:
    task, session, path = _claimed_workspace(plane)
    (path / "app.py").write_text("value = 1\n# reviewed change\n")
    plane.checkpoint(task, session, checkpoint())
    assert verify(plane, task, session)["status"] == "PASS"
    run_git(["add", "app.py"], cwd=path)
    run_git(["commit", "-m", "verified task"], cwd=path)
    return task, session, path


def test_a_primary_changed_after_the_gate_stops_the_merge(
    repo: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The gate passes, then the primary changes before the merge reads it again.
    task, session, path = _verified_workspace(repo)
    passed = workspaces.integration_gate

    def change_primary(plane: Any, task_id: str, token: str) -> Any:
        result = passed(plane, task_id, token)
        (plane.root / "notes.txt").write_text("changed after the gate\n")
        return result

    monkeypatch.setattr(workspaces, "integration_gate", change_primary)

    _rejects(
        "BASELINE_CHANGED",
        "Refresh the integration baseline",
        merge_workspace,
        repo,
        task,
        session,
    )
    assert repo.store.get(task, "task")["state"] != "COMPLETED"


def test_merge_refuses_when_the_merge_did_not_reproduce_the_workspace(
    repo: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A merge that leaves the primary different from the reviewed workspace, as a
    # hook rewriting files would, must not be recorded as integrated.
    task, session, _ = _verified_workspace(repo)
    real = workspaces.run_git

    def merge_nothing(arguments: list[str], cwd: Path | None = None) -> str:
        return "" if arguments[0] == "merge" else real(arguments, cwd=cwd)

    monkeypatch.setattr(workspaces, "run_git", merge_nothing)

    _rejects(
        "INTEGRATION_MISMATCH",
        "Merged files differ; task remains uncompleted",
        merge_workspace,
        repo,
        task,
        session,
    )
    assert not repo.store.get(task, "task")["integration"].get("merge_performed")


def test_merge_refuses_when_only_the_links_differ_afterwards(
    repo: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    task, session, _ = _verified_workspace(repo)
    real_git, real_links = workspaces.run_git, workspaces.link_fingerprint
    merged: list[bool] = []

    def run_git(arguments: list[str], cwd: Path | None = None) -> str:
        output = real_git(arguments, cwd=cwd)
        merged.append(arguments[0] == "merge")
        return output

    def links(root: Path) -> dict[str, str]:
        measured = real_links(root)
        if any(merged) and root == repo.root:
            return {**measured, "added-by-merge": "link"}
        return measured

    monkeypatch.setattr(workspaces, "run_git", run_git)
    monkeypatch.setattr(workspaces, "link_fingerprint", links)

    _rejects(
        "INTEGRATION_MISMATCH",
        "Merged files differ; task remains uncompleted",
        merge_workspace,
        repo,
        task,
        session,
    )


def test_a_workspace_recorded_before_links_were_measured_still_merges(repo: Any) -> None:
    # Workspaces created before link baselines existed carry no `baseline_links`;
    # a repository without links matches that missing baseline.
    task, session, _ = _verified_workspace(repo)
    workspace_id = repo.store.get(task, "task")["workspace_id"]
    with repo.store.transaction():
        current = repo.store.get(workspace_id, "workspace")
        legacy = {key: value for key, value in current.items() if key != "baseline_links"}
        repo.store.put("workspace", legacy, expected=current["version"])

    assert merge_workspace(repo, task, session)["merge_performed"] is True


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlinks")
def test_verify_refuses_an_evidence_directory_a_verifier_replaced_with_a_link(
    project: Any,
) -> None:
    # The directory is checked before the run starts, and again before each artifact
    # is written, because the verifier itself runs in between.
    swap = (
        "import os, shutil; target = '.agentic/control/evidence'; "
        "shutil.rmtree(target, ignore_errors=True); os.makedirs('elsewhere', exist_ok=True); "
        "os.symlink(os.path.abspath('elsewhere'), target)"
    )
    verification = [{"kind": "unit", "command": [sys.executable, "-c", swap], "acceptance": [0]}]
    task, session = _claimed(project, verification=verification)

    _rejects(
        "INVALID_PATH",
        "Evidence directory must not be a symlink",
        verify,
        project,
        task,
        session,
    )
    assert project.store.get(task, "task")["state"] == "FAILED"
    assert not list((project.root / "elsewhere").iterdir())
