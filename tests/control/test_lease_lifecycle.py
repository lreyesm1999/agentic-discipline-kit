"""What a heartbeat, an expiry sweep and a cancellation write to the records.

Ownership is decided by lease records: a heartbeat must refresh both the lease and
the agent behind it, an expiry sweep must reach every lease that ran out, and a
cancelled task must revoke its own leases and no others. Existing tests assert the
lease written when a task is claimed and the refusals around it, so the writes that
follow were free to touch another field, stop at the first record, or revoke a
lease belonging to another task. Each case compares the records whole.
"""

from __future__ import annotations

import time
from typing import Any

from conftest import contract

CAPABILITIES = ["code", "terminal"]


def _force(project: Any, kind: str, identifier: str, **fields: Any) -> dict[str, Any]:
    with project.store.transaction():
        current = project.store.get(identifier, kind)
        return project.store.put(kind, {**current, **fields}, expected=current["version"])


def _ready(project: Any) -> str:
    data = contract()
    project.approve_command(data["verification"][0]["command"])
    task = project.create_task(data)["id"]
    project.ready(task)
    return str(task)


def _expired_lease(project: Any, name: str) -> dict[str, Any]:
    """Claim a task, then leave its lease active but already run out."""
    task = _ready(project)
    lease = project.claim(task, project.join(name, CAPABILITIES)["session"])
    return _force(project, "lease", lease["id"], state="ACTIVE", expires_at=time.time() - 1)


def test_a_heartbeat_refreshes_the_lease_and_the_agent_behind_it(project: Any) -> None:
    task = _ready(project)
    agent = project.join("worker", CAPABILITIES)
    lease = project.claim(task, agent["session"], 60)
    joined = project.store.get(agent["id"], "agent")
    stale = _force(project, "agent", agent["id"], heartbeat_at=1000.0)

    before = time.time()
    refreshed = project.heartbeat(task, agent["session"], 120)
    after = time.time()

    assert refreshed == {
        **lease,
        "version": lease["version"] + 1,
        "heartbeat_at": refreshed["heartbeat_at"],
        "expires_at": refreshed["expires_at"],
    }
    assert before <= refreshed["heartbeat_at"] <= after
    assert before + 120 <= refreshed["expires_at"] <= after + 120

    current = project.store.get(agent["id"], "agent")
    assert current == {
        **joined,
        "version": stale["version"] + 1,
        "heartbeat_at": current["heartbeat_at"],
    }
    assert before <= current["heartbeat_at"] <= after


def test_every_lease_that_ran_out_is_swept_not_only_the_first(project: Any) -> None:
    # Two leases have run out; a sweep that stops at the first leaves the other owning a task.
    first = _expired_lease(project, "first")
    second = _expired_lease(project, "second")

    newcomer = _ready(project)
    project.claim(newcomer, project.join("third", CAPABILITIES)["session"])

    assert project.store.get(first["id"], "lease")["state"] == "EXPIRED"
    assert project.store.get(second["id"], "lease")["state"] == "EXPIRED"
    for lease in (first, second):
        assert project.store.get(lease["task_id"], "task")["state"] == "READY"


def _seed_lease(project: Any, identifier: str, task_id: str, agent_id: str) -> dict[str, Any]:
    """Insert a lease that has run out, under a chosen id so sweep order is fixed."""
    with project.store.transaction():
        return project.store.put(
            "lease",
            {
                "id": identifier,
                "task_id": task_id,
                "agent_id": agent_id,
                "acquired_at": time.time(),
                "heartbeat_at": time.time(),
                "expires_at": time.time() - 1,
                "state": "ACTIVE",
            },
        )


def test_a_lease_kept_by_a_running_verifier_does_not_end_the_sweep(project: Any) -> None:
    # The protected lease is swept first; the one behind it must still be expired.
    protected_task, plain_task = _ready(project), _ready(project)
    agent = project.join("worker", CAPABILITIES)
    _force(
        project,
        "task",
        protected_task,
        state="CLAIMED",
        active_run="RUN-1",
        active_run_deadline=time.time() + 60,
    )
    _force(project, "task", plain_task, state="CLAIMED")
    protected = _seed_lease(project, "LEAS-a-protected", protected_task, agent["id"])
    plain = _seed_lease(project, "LEAS-b-plain", plain_task, agent["id"])

    project.status()

    assert project.store.get(protected["id"], "lease") == protected
    assert project.store.get(plain["id"], "lease")["state"] == "EXPIRED"
    assert project.store.get(protected_task, "task")["state"] == "CLAIMED"
    assert project.store.get(plain_task, "task")["state"] == "READY"


def test_cancelling_revokes_the_leases_of_that_task_and_no_others(project: Any) -> None:
    cancelled = _ready(project)
    owner = project.claim(cancelled, project.join("owner", CAPABILITIES)["session"])
    stranger = _ready(project)
    with project.store.transaction():
        other = project.store.put(
            "lease",
            {
                "id": "LEAS-stranger",
                "task_id": stranger,
                "agent_id": owner["agent_id"],
                "acquired_at": time.time(),
                "heartbeat_at": time.time(),
                "expires_at": time.time() + 300,
                "state": "ACTIVE",
            },
        )

    result = project.transition(cancelled, "CANCELLED", "Requirement withdrawn")

    assert (result["state"], result["disposition_reason"]) == ("CANCELLED", "Requirement withdrawn")
    assert project.store.get(owner["id"], "lease") == {
        **owner,
        "version": owner["version"] + 1,
        "state": "REVOKED",
    }
    assert project.store.get(other["id"], "lease") == other
