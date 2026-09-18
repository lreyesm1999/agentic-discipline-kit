"""The two guards that refuse to start a second verifier run.

`verify` checks for a run in flight before it does any work, and checks again
inside the transaction that starts one, because the record can gain a run between
the two reads. The first refusal was asserted but not its effect, and the second
guard was never reached at all, so both were free to read another field or refuse
with another code. Each case pins the refusal and the record it must leave alone.
"""

from __future__ import annotations

from typing import Any

import pytest
from conftest import contract

from agentic_discipline.control import verification
from agentic_discipline.control.contracts import ControlError
from agentic_discipline.control.verification import verify


def _force(plane: Any, kind: str, identifier: str, **fields: Any) -> dict[str, Any]:
    with plane.store.transaction():
        current = plane.store.get(identifier, kind)
        return plane.store.put(kind, {**current, **fields}, expected=current["version"])


def _claimed(plane: Any) -> tuple[str, str]:
    data = contract()
    plane.approve_command(data["verification"][0]["command"])
    task = plane.create_task(data)["id"]
    plane.ready(task)
    session = plane.join("worker", ["code", "terminal"])["session"]
    plane.claim(task, session)
    return task, session


def test_a_run_already_in_flight_is_refused_and_left_untouched(project: Any) -> None:
    task, session = _claimed(project)
    _force(project, "task", task, active_run="RUN-1")
    before = project.store.get(task, "task")

    with pytest.raises(ControlError) as caught:
        verify(project, task, session)

    assert (caught.value.code, str(caught.value)) == (
        "VERIFICATION_BUSY",
        "A verifier is already running",
    )
    after = project.store.get(task, "task")
    assert (after["active_run"], after["attempts"], after["state"]) == (
        "RUN-1",
        before["attempts"],
        before["state"],
    )


def test_a_run_started_between_the_two_reads_is_refused(
    project: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The record gains a run after the first guard passes, so only the second sees it.
    task, session = _claimed(project)
    original = verification.check_changes

    def start_a_run(plane: Any, current: dict[str, Any]) -> None:
        original(plane, current)
        if not plane.store.get(task, "task").get("active_run"):
            _force(plane, "task", task, active_run="RUN-2")

    monkeypatch.setattr(verification, "check_changes", start_a_run)

    with pytest.raises(ControlError) as caught:
        verify(project, task, session)

    assert (caught.value.code, str(caught.value)) == (
        "VERIFICATION_BUSY",
        "A verifier is already running",
    )
    assert project.store.get(task, "task")["active_run"] == "RUN-2"
