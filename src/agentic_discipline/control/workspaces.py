"""Git worktrees and conservative semantic integration, without automatic merges."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..common import run_git
from .contracts import digest, require, uid
from .discovery import fingerprint, git, line_counts, link_fingerprint, validate_inputs
from .plane import Plane
from .verification import binding, completion_proof


def parallel_safety(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    overlap = [
        (a, b)
        for a in left["scope"]
        for b in right["scope"]
        if a == "."
        or b == "."
        or a == b
        or a.startswith(b.rstrip("/") + "/")
        or b.startswith(a.rstrip("/") + "/")
    ]
    boundaries = sorted(set(left["boundaries"]) & set(right["boundaries"]))
    status = (
        "CONFLICTING"
        if overlap
        else "SERIALIZE"
        if boundaries
        else "PARALLEL_WITH_REVIEW"
        if left["risk"] in {"HIGH", "CRITICAL"} or right["risk"] in {"HIGH", "CRITICAL"}
        else "SAFE_PARALLEL"
    )
    return {"status": status, "path_overlap": overlap, "shared_boundaries": boundaries}


def create_workspace(plane: Plane, task_id: str) -> dict[str, Any]:
    task = plane.store.get(task_id, "task")
    require(not task.get("workspace_id"), "WORKSPACE_EXISTS", "Task already has a workspace")
    require(
        task["state"] in {"PLANNED", "READY"},
        "INVALID_TRANSITION",
        "Allocate isolation before claiming",
    )
    base = git(plane.root, ["rev-parse", "HEAD"])
    require(
        base and not git(plane.root, ["diff", "HEAD", "--name-only"]),
        "DIRTY_BASELINE",
        "Commit the reviewed baseline before creating worktrees",
    )
    directory = plane.directory / "worktrees" / task_id
    require(
        not directory.parent.is_symlink(), "INVALID_PATH", "Workspace parent cannot be a symlink"
    )
    directory.parent.mkdir(exist_ok=True)
    branch = "agentic/" + task_id.lower()
    run_git(["worktree", "add", "-b", branch, str(directory), base], cwd=plane.root)
    try:
        with plane.store.transaction():
            current = plane.store.get(task_id, "task")
            require(
                current["version"] == task["version"],
                "VERSION_CONFLICT",
                "Task changed during workspace creation",
            )
            record = plane.store.put(
                "workspace",
                {
                    "id": uid("WSP"),
                    "task_id": task_id,
                    "path": str(directory),
                    "branch": branch,
                    "base_commit": base,
                    "baseline_files": fingerprint(plane.root),
                    "baseline_links": link_fingerprint(plane.root),
                    "status": "ACTIVE",
                },
            )
            plane.store.put(
                "task", {**current, "workspace_id": record["id"]}, expected=current["version"]
            )
            return record
    except BaseException:
        run_git(["worktree", "remove", str(directory)], cwd=plane.root)
        raise


def integration_gate(plane: Plane, task_id: str, session: str) -> dict[str, Any]:
    task, lease = plane.owned(task_id, session)
    require(task.get("workspace_id"), "NO_WORKSPACE", "Task uses the primary repository")
    workspace = plane.store.get(task["workspace_id"], "workspace")
    validate_inputs(plane.root, plane.policy()["protected_paths"])
    require(
        git(plane.root, ["rev-parse", "HEAD"]) == workspace["base_commit"],
        "BASELINE_CHANGED",
        "Refresh/rebase the workspace before integration",
    )
    require(
        fingerprint(plane.root) == workspace["baseline_files"]
        and link_fingerprint(plane.root) == workspace.get("baseline_links", {}),
        "BASELINE_CHANGED",
        "Primary workspace changed outside the task",
    )
    completion_proof(plane, task)
    for other in plane.store.list("task"):
        if other["id"] != task_id and other["state"] in {"CLAIMED", "RUNNING", "VERIFYING"}:
            require(
                parallel_safety(task, other)["status"] == "SAFE_PARALLEL",
                "SEMANTIC_CONFLICT",
                "Concurrent task needs serialization or explicit review",
            )
    result = {
        "status": "PASS",
        "binding": digest(binding(plane, task)),
        "target_commit": workspace["base_commit"],
        "merge_performed": False,
    }
    with plane.store.transaction():
        current, _ = plane.owned(task_id, session)
        plane.store.put(
            "task",
            {**current, "integration": result},
            expected=current["version"],
            actor=lease["agent_id"],
        )
    return result


def cleanup(plane: Plane, task_id: str) -> dict[str, Any]:
    task = plane.store.get(task_id, "task")
    require(
        task["state"] in {"COMPLETED", "CANCELLED", "SUPERSEDED"} and task.get("workspace_id"),
        "WORKSPACE_BUSY",
        "Preserve workspace for active work",
    )
    workspace = plane.store.get(task["workspace_id"], "workspace")
    path = Path(workspace["path"])
    require(
        path.parent == plane.directory / "worktrees"
        and not path.is_symlink()
        and not path.parent.is_symlink(),
        "INVALID_PATH",
        "Unmanaged workspace",
    )
    run_git(["worktree", "remove", str(path)], cwd=plane.root)
    with plane.store.transaction():
        return plane.store.put(
            "workspace", {**workspace, "status": "REMOVED"}, expected=workspace["version"]
        )


def refresh_workspace(plane: Plane, task_id: str) -> dict[str, Any]:
    """Rebase clean work onto the current baseline; stop cleanly on text conflicts."""
    task = plane.store.get(task_id, "task")
    require(
        task.get("workspace_id")
        and not task.get("active_run")
        and task["state"] not in {"COMPLETED", "CANCELLED", "SUPERSEDED"},
        "WORKSPACE_BUSY",
        "An idle isolated workspace is required",
    )
    workspace = plane.store.get(task["workspace_id"], "workspace")
    directory = plane.workspace_root(task)
    require(
        not git(directory, ["status", "--porcelain"]),
        "DIRTY_WORKSPACE",
        "Commit or checkpoint local edits before refreshing",
    )
    target = git(plane.root, ["rev-parse", "HEAD"])
    require(
        target and not git(plane.root, ["diff", "HEAD", "--name-only"]),
        "DIRTY_BASELINE",
        "Primary baseline must be committed",
    )
    try:
        run_git(["rebase", target], cwd=directory)
    except RuntimeError:
        if git(directory, ["rev-parse", "--verify", "REBASE_HEAD"]):
            run_git(["rebase", "--abort"], cwd=directory)
        raise
    with plane.store.transaction():
        current = plane.store.get(task_id, "task")
        require(
            current["version"] == task["version"],
            "VERSION_CONFLICT",
            "Task changed while refreshing; reconcile workspace",
        )
        plane.store.put(
            "task",
            {
                **current,
                "integration": None,
                "initial_files": fingerprint(plane.root),
                "initial_links": link_fingerprint(plane.root),
                "initial_line_counts": line_counts(plane.root, list(fingerprint(plane.root))),
            },
            expected=current["version"],
        )
        return plane.store.put(
            "workspace",
            {
                **workspace,
                "base_commit": target,
                "baseline_files": fingerprint(plane.root),
                "baseline_links": link_fingerprint(plane.root),
            },
            expected=workspace["version"],
        )


def merge_workspace(plane: Plane, task_id: str, session: str) -> dict[str, Any]:
    """Explicit owner-side integration; merge only a verified fast-forward branch."""
    task, _ = plane.owned(task_id, session)
    require(task.get("workspace_id"), "NO_WORKSPACE", "Task uses the primary repository")
    workspace = plane.store.get(task["workspace_id"], "workspace")
    directory = plane.workspace_root(task)
    target = git(directory, ["rev-parse", "HEAD"])
    validate_inputs(plane.root, plane.policy()["protected_paths"])
    current_head = git(plane.root, ["rev-parse", "HEAD"])
    if current_head != workspace["base_commit"] and current_head == target:
        # Git and SQLite cannot share one transaction. Recover only the exact
        # previously gated tree after a successful merge and failed DB commit.
        completion_proof(plane, task)
        require(
            task.get("integration")
            and task["integration"]["status"] == "PASS"
            and task["integration"]["binding"] == digest(binding(plane, task))
            and fingerprint(plane.root) == fingerprint(directory)
            and link_fingerprint(plane.root) == link_fingerprint(directory),
            "INTEGRATION_MISMATCH",
            "Cannot recover a merge whose reviewed contents changed",
        )
        with plane.store.transaction():
            current, lease = plane.owned(task_id, session)
            require(
                current["version"] == task["version"],
                "VERSION_CONFLICT",
                "Task changed during merge recovery",
            )
            result = {
                **task["integration"],
                "merge_performed": True,
                "merged_commit": target,
                "merged_files": fingerprint(plane.root),
                "recovered": True,
            }
            plane.store.put(
                "task",
                {**current, "integration": result},
                expected=current["version"],
                actor=lease["agent_id"],
            )
            plane.store.event(
                lease["agent_id"],
                "workspace.merge_recovered",
                {"task_id": task_id, "commit": target},
            )
            return result
    integration_gate(plane, task_id, session)
    with plane.store.transaction():
        task, lease = plane.owned(task_id, session)
        workspace = plane.store.get(task["workspace_id"], "workspace")
        directory = plane.workspace_root(task)
        require(
            not git(directory, ["status", "--porcelain"]),
            "DIRTY_WORKSPACE",
            "Commit verified changes before merging",
        )
        target = git(directory, ["rev-parse", "HEAD"])
        primary_head = git(plane.root, ["rev-parse", "HEAD"])
        require(
            primary_head == workspace["base_commit"]
            and fingerprint(plane.root) == workspace["baseline_files"]
            and link_fingerprint(plane.root) == workspace.get("baseline_links", {}),
            "BASELINE_CHANGED",
            "Refresh the integration baseline",
        )
        # The task branch must contain the exact reviewed baseline. No merge conflict
        # resolution or force update is hidden inside the integration operation.
        run_git(["merge-base", "--is-ancestor", primary_head, target], cwd=plane.root)
        run_git(["merge", "--ff-only", "--", workspace["branch"]], cwd=plane.root)
        require(
            fingerprint(plane.root) == fingerprint(directory)
            and link_fingerprint(plane.root) == link_fingerprint(directory),
            "INTEGRATION_MISMATCH",
            "Merged files differ; task remains uncompleted",
        )
        result = {
            **task["integration"],
            "merge_performed": True,
            "merged_commit": target,
            "merged_files": fingerprint(plane.root),
        }
        plane.store.put(
            "task",
            {**task, "integration": result},
            expected=task["version"],
            actor=lease["agent_id"],
        )
        plane.store.event(
            lease["agent_id"], "workspace.merged", {"task_id": task_id, "commit": target}
        )
        return result
