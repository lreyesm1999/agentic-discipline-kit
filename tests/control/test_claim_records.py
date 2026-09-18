"""Task claims, record by record.

Claiming is how an agent takes ownership: it expires stale leases, records the
file, link and line baselines later budget checks compare against, and writes
the lease. Existing tests asserted each refusal and the lease state, so a
baseline could be taken from the wrong tree, a lease could get the wrong expiry,
or an expired owner could keep blocking the task unnoticed. Each case compares
the written records whole.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest
from conftest import contract
from test_workspaces import repository

from agentic_discipline.control.contracts import ControlError
from agentic_discipline.control.discovery import fingerprint, line_counts, link_fingerprint
from agentic_discipline.control.plane import Plane
from agentic_discipline.control.workspaces import create_workspace

CAPABILITIES = ["code", "terminal"]


def _ready(plane: Any, **changes: Any) -> str:
    data = {**contract(), **changes}
    plane.approve_command(data["verification"][0]["command"])
    task = plane.create_task(data)["id"]
    plane.ready(task)
    return task


def _force(plane: Any, kind: str, identifier: str, **fields: Any) -> dict[str, Any]:
    with plane.store.transaction():
        current = plane.store.get(identifier, kind)
        return plane.store.put(kind, {**current, **fields}, expected=current["version"])


def _writer(plane: Any, kind: str, record: dict[str, Any]) -> str:
    rows = plane.store.db.execute(
        "SELECT actor, payload FROM events WHERE action = ? ORDER BY seq", (f"{kind}.write",)
    )
    (actor,) = [
        r["actor"]
        for r in rows
        if json.loads(r["payload"])["id"] == record["id"]
        and json.loads(r["payload"])["version"] == record["version"]
    ]
    return actor


def _rejects(code: str, message: str, action: Any, *args: Any) -> None:
    with pytest.raises(ControlError) as caught:
        action(*args)
    assert (caught.value.code, str(caught.value)) == (code, message)


def _baselines(workspace: Path) -> dict[str, Any]:
    return {
        "initial_files": fingerprint(workspace),
        "initial_links": link_fingerprint(workspace),
        "initial_line_counts": line_counts(workspace, list(fingerprint(workspace))),
    }


@pytest.mark.parametrize("seconds", [None, 120])
def test_claim_writes_the_lease_and_the_task_baselines(project: Any, seconds: int | None) -> None:
    task_id = _ready(project)
    agent = project.join("worker", CAPABILITIES)
    ready = project.store.get(task_id, "task")
    lifetime = 300 if seconds is None else seconds

    before = time.time()
    arguments = () if seconds is None else (seconds,)
    lease = project.claim(task_id, agent["session"], *arguments)
    after = time.time()

    assert lease["id"].startswith("LEAS-")
    assert lease == {
        "id": lease["id"],
        "version": 1,
        "task_id": task_id,
        "agent_id": agent["id"],
        "acquired_at": lease["acquired_at"],
        "heartbeat_at": lease["heartbeat_at"],
        "expires_at": lease["expires_at"],
        "state": "ACTIVE",
    }
    assert before <= lease["acquired_at"] <= lease["heartbeat_at"] <= after
    assert before + lifetime <= lease["expires_at"] <= after + lifetime
    assert project.store.get(lease["id"], "lease") == lease

    claimed = project.store.get(task_id, "task")
    assert claimed == {
        **ready,
        "version": ready["version"] + 1,
        "state": "CLAIMED",
        **_baselines(project.root),
    }
    assert _writer(project, "task", claimed) == agent["id"]
    assert _writer(project, "lease", lease) == agent["id"]


def test_claim_keeps_baselines_recorded_before_it(project: Any) -> None:
    task_id = _ready(project)
    recorded = {
        "initial_files": {"app.py": "recorded"},
        "initial_links": {"docs": "recorded"},
        "initial_line_counts": {"app.py": 7},
    }
    ready = _force(project, "task", task_id, **recorded)

    project.claim(task_id, project.join("worker", CAPABILITIES)["session"])

    assert project.store.get(task_id, "task") == {
        **ready,
        "version": ready["version"] + 1,
        "state": "CLAIMED",
    }


def test_an_expired_owner_no_longer_blocks_the_task(project: Any) -> None:
    task_id = _ready(project)
    first = project.join("first", CAPABILITIES)
    second = project.join("second", CAPABILITIES)
    old = project.claim(task_id, first["session"])
    old = _force(project, "lease", old["id"], expires_at=time.time() - 1)

    lease = project.claim(task_id, second["session"])

    assert project.store.get(old["id"], "lease") == {
        **old,
        "version": old["version"] + 1,
        "state": "EXPIRED",
    }
    assert (lease["agent_id"], lease["state"]) == (second["id"], "ACTIVE")
    assert project.store.get(task_id, "task")["state"] == "CLAIMED"


def test_an_expired_owner_with_a_running_verifier_keeps_the_task(project: Any) -> None:
    task_id = _ready(project)
    old = project.claim(task_id, project.join("first", CAPABILITIES)["session"])
    old = _force(project, "lease", old["id"], expires_at=time.time() - 1)
    _force(project, "task", task_id, active_run="RUN-1", active_run_deadline=time.time() + 60)

    second = project.join("second", CAPABILITIES)["session"]
    _rejects("NOT_READY", "Task is not available", project.claim, task_id, second)
    assert project.store.get(old["id"], "lease") == old


def test_shortest_lease_and_exactly_matching_capabilities_are_accepted(project: Any) -> None:
    task_id = _ready(project, capabilities=["database"])
    agent = project.join("database specialist", ["database"])
    before = time.time()
    lease = project.claim(task_id, agent["session"], 1)
    assert (lease["agent_id"], lease["state"]) == (agent["id"], "ACTIVE")
    assert before + 1 <= lease["expires_at"] <= time.time() + 1


@pytest.mark.parametrize("state", ["CLAIMED", "RUNNING", "VERIFYING", "FAILED"])
def test_expiry_returns_unfinished_work_to_ready(project: Any, state: str) -> None:
    task_id = _ready(project)
    lease = project.claim(task_id, project.join("worker", CAPABILITIES)["session"])
    lease = _force(project, "lease", lease["id"], expires_at=time.time() - 1)
    # The verifier deadline already passed, so the run no longer protects the lease.
    task = _force(
        project, "task", task_id, state=state, active_run="RUN-1", active_run_deadline=1.0
    )

    with project.store.transaction():
        project._expire()

    assert project.store.get(lease["id"], "lease") == {
        **lease,
        "version": lease["version"] + 1,
        "state": "EXPIRED",
    }
    assert project.store.get(task_id, "task") == {
        **task,
        "version": task["version"] + 1,
        "state": "READY",
        "active_run": None,
    }


def test_expiry_leaves_finished_work_alone(project: Any) -> None:
    task_id = _ready(project)
    lease = project.claim(task_id, project.join("worker", CAPABILITIES)["session"])
    _force(project, "lease", lease["id"], expires_at=time.time() - 1)
    task = _force(project, "task", task_id, state="COMPLETED")

    with project.store.transaction():
        project._expire()

    assert project.store.get(lease["id"], "lease")["state"] == "EXPIRED"
    assert project.store.get(task_id, "task") == task


def test_leases_that_are_no_longer_active_do_not_serialize_other_work(project: Any) -> None:
    first_task, second_task = _ready(project), _ready(project)
    lease = project.claim(first_task, project.join("first", CAPABILITIES)["session"])
    _force(project, "lease", lease["id"], state="RELEASED")

    second = project.join("second", CAPABILITIES)
    assert project.claim(second_task, second["session"])["agent_id"] == second["id"]


def test_workspace_claims_take_baselines_from_the_workspace(tmp_path: Path) -> None:
    repository(tmp_path)
    with Plane(tmp_path) as plane:
        data = contract()
        plane.approve_command(data["verification"][0]["command"])
        task_id = plane.create_task(data)["id"]
        workspace = Path(create_workspace(plane, task_id)["path"])
        (workspace / "only_in_workspace.py").write_text("value = 1\n", encoding="utf-8")
        plane.ready(task_id)

        plane.claim(task_id, plane.join("isolated", CAPABILITIES)["session"])

        claimed = plane.store.get(task_id, "task")
        assert {key: claimed[key] for key in _baselines(workspace)} == _baselines(workspace)
        assert "only_in_workspace.py" in claimed["initial_files"]


def test_parallel_work_needs_a_workspace_for_both_tasks(tmp_path: Path) -> None:
    repository(tmp_path)
    with Plane(tmp_path) as plane:
        isolated = {**contract(), "scope": ["left.py"], "boundaries": ["left"]}
        shared = {**contract(), "scope": ["right.py"], "boundaries": ["right"]}
        tasks = []
        for data in (isolated, shared):
            plane.approve_command(data["verification"][0]["command"])
            tasks.append(plane.create_task(data)["id"])
        create_workspace(plane, tasks[0])
        for task_id in tasks:
            plane.ready(task_id)

        plane.claim(tasks[0], plane.join("left", CAPABILITIES)["session"])
        _rejects(
            "PARALLEL_CONFLICT",
            "Concurrent work requires isolated workspaces and disjoint contracts",
            plane.claim,
            tasks[1],
            plane.join("right", CAPABILITIES)["session"],
        )
