"""The completion path's guards and the stamps that bind evidence to obligations.

Completion checks the task's state twice: once before the proof is gathered, so a caller
gets the 2.0 diagnostic it already acts on, and again inside the transaction that writes,
in case the state moved in between. The second check is defence in depth, so it is reached
here by letting the first one see a state that has since changed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from assurance_support import claimed, contract, sources, spec

from agentic_discipline.control import verification
from agentic_discipline.control.assurance import resolver, service
from agentic_discipline.control.contracts import ControlError
from agentic_discipline.control.plane import Plane, adopt


@pytest.fixture
def plane(tmp_path: Path) -> Any:
    sources(tmp_path, {"src/report.py": "value = 1\n"})
    adopt(tmp_path)
    with Plane(tmp_path) as opened:
        yield opened


def test_the_state_is_checked_again_inside_the_transaction_that_completes(
    plane: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    task, session = claimed(plane, contract())
    real = plane.owned
    calls = {"count": 0}

    def first_sees_verifying(task_id: str, token: str) -> Any:
        record, lease = real(task_id, token)
        calls["count"] += 1
        # Only the check in front of the transaction is told the task was verified.
        return ({**record, "state": "VERIFYING"} if calls["count"] == 1 else record), lease

    monkeypatch.setattr(plane, "owned", first_sees_verifying)
    monkeypatch.setattr(verification, "completion_proof", lambda plane, task: None)
    monkeypatch.setattr(verification, "assurance_gate", lambda plane, task_id: [])

    with pytest.raises(ControlError) as refused:
        verification.complete(plane, task, session)

    assert (refused.value.code, str(refused.value)) == (
        "INVALID_TRANSITION",
        "Only a verified task can complete",
    )
    assert calls["count"] == 2


def test_proof_debt_names_every_open_claim(plane: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    task, session = claimed(plane, contract())
    record, lease = plane.owned(task, session)
    monkeypatch.setattr(
        plane, "owned", lambda task_id, token: ({**record, "state": "VERIFYING"}, lease)
    )
    monkeypatch.setattr(verification, "completion_proof", lambda plane, task: None)
    monkeypatch.setattr(
        verification,
        "assurance_gate",
        lambda plane, task_id: [
            {"obligation_id": "PO-1", "status": "STALE"},
            {"obligation_id": "PO-2", "status": "UNKNOWN"},
        ],
    )

    with pytest.raises(ControlError) as refused:
        verification.complete(plane, task, session)

    assert (refused.value.code, str(refused.value)) == (
        "PROOF_DEBT",
        "Mandatory proof obligations are unresolved: PO-1 STALE; PO-2 UNKNOWN",
    )


def _two_criteria(plane: Any) -> str:
    task, _ = claimed(
        plane,
        contract(
            acceptance=["The reported value is one", "The report is written once"],
            verification=[spec("unit", [0, 1])],
        ),
    )
    service.compile_plan(plane, task, phase="INITIAL")
    return task


def test_each_verifier_is_stamped_with_every_obligation_it_runs_for_in_order(
    plane: Any,
) -> None:
    task = _two_criteria(plane)
    obligations = sorted(
        o["id"] for o in service.obligations_for(plane, task) if o["derivation"] == "CONTRACT"
    )

    stamps = verification.assurance_stamps(plane, plane.store.get(task, "task"))

    (stamp,) = [
        entry for entry in stamps.values() if set(obligations) <= set(entry["obligation_ids"])
    ]
    assert stamp["obligation_ids"] == sorted(stamp["obligation_ids"])
    assert set(stamp) == {"obligation_ids", "obligation_bindings"}
    assert set(stamp["obligation_bindings"]) == set(stamp["obligation_ids"])


def test_an_obligation_that_cannot_be_bound_does_not_stop_the_others_from_being_stamped(
    plane: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = _two_criteria(plane)
    ordered = [o["id"] for o in service.obligations_for(plane, task)]
    real = resolver.obligation_binding

    def first_cannot_be_bound(plane: Any, task: Any, obligation: Any) -> Any:
        if obligation["id"] == ordered[0]:
            raise ControlError("INVALID_PATH", "cannot be read")
        return real(plane, task, obligation)

    monkeypatch.setattr(resolver, "obligation_binding", first_cannot_be_bound)

    stamps = verification.assurance_stamps(plane, plane.store.get(task, "task"))

    stamped = {identifier for entry in stamps.values() for identifier in entry["obligation_ids"]}
    assert ordered[0] not in stamped
    assert set(ordered[1:]) <= stamped
