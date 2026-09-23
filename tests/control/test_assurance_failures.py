"""Failure injection and the integrity surfaces an agent could try to work around.

Each case does the damage for real - deletes an artefact, rewrites a hash, kills a run
mid-flight, spends the runtime budget - and then asks what the engine now claims.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import pytest
from assurance_support import BUDGET, FAILS, PASSES, claimed, contract, sources, spec

from agentic_discipline.control.assurance import resolver, service
from agentic_discipline.control.assurance.resolver import obligations_for
from agentic_discipline.control.contracts import ControlError, digest
from agentic_discipline.control.plane import Plane, adopt
from agentic_discipline.control.verification import complete, verify

SLEEPS = [sys.executable, "-c", "import time; time.sleep(30)"]


@pytest.fixture
def repository(tmp_path: Path) -> Any:
    sources(tmp_path, {"src/report.py": "value = 1\n", "src/report_test.py": "assert True\n"})
    adopt(tmp_path)
    with Plane(tmp_path) as plane:
        yield plane


def _verified(repository: Any) -> tuple[str, str, dict[str, Any]]:
    task_id, session = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    obligation = obligations_for(repository, task_id)[0]
    task = repository.store.get(task_id, "task")
    evidence = resolver.task_evidence(repository, task_id)
    assert resolver.resolve(repository, task, obligation, evidence=evidence)["status"] == "VERIFIED"
    return task_id, session, obligation


def _status(repository: Any, task_id: str, obligation: dict[str, Any]) -> str:
    task = repository.store.get(task_id, "task")
    evidence = resolver.task_evidence(repository, task_id)
    return str(resolver.resolve(repository, task, obligation, evidence=evidence)["status"])


# --- artefacts ------------------------------------------------------------------------


def test_a_deleted_evidence_artefact_stops_proving_its_claim(repository: Any) -> None:
    task_id, _, obligation = _verified(repository)
    record = repository.store.list("evidence")[0]

    (repository.directory / "evidence" / f"{record['id']}.json").unlink()

    assert _status(repository, task_id, obligation) == "STALE"


def test_a_rewritten_evidence_artefact_stops_proving_its_claim(repository: Any) -> None:
    task_id, _, obligation = _verified(repository)
    record = repository.store.list("evidence")[0]
    artifact = repository.directory / "evidence" / f"{record['id']}.json"

    payload = json.loads(artifact.read_text(encoding="utf-8"))
    artifact.write_text(json.dumps({**payload, "exit_code": 0, "result": "PASS"}), encoding="utf-8")

    assert _status(repository, task_id, obligation) == "STALE"


def test_relabelling_a_stored_result_as_pass_does_not_restore_the_claim(
    repository: Any,
) -> None:
    """The artefact hash is what a verdict rests on, not the row that names it."""
    task_id, session = claimed(repository, contract(verification=[spec("unit", [0], FAILS)]))
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    obligation = obligations_for(repository, task_id)[0]
    record = repository.store.list("evidence")[0]

    with repository.store.transaction():
        repository.store.put("evidence", {**record, "result": "PASS"}, expected=record["version"])

    # The row says PASS; the artefact it points at still holds exit code 1, and wins.
    artifact = repository.directory / "evidence" / f"{record['id']}.json"
    assert json.loads(artifact.read_text(encoding="utf-8"))["exit_code"] == 1
    assert _status(repository, task_id, obligation) == "STALE"
    assert service.status(repository, task_id)["tasks"][0]["proof_debt"] == 1


# --- runs -----------------------------------------------------------------------------


def test_a_verifier_that_cannot_start_leaves_the_claim_blocked_not_passed(
    repository: Any,
) -> None:
    task_id, session = claimed(
        repository, contract(verification=[spec("unit", [0], ["no-such-verifier-binary"])])
    )
    service.compile_plan(repository, task_id, phase="INITIAL")

    outcome = service.verify(repository, task_id, session)

    record = repository.store.list("evidence")[0]
    assert (record["result"], record["exit_code"]) == ("BLOCKED", 127)
    assert _status(repository, task_id, obligations_for(repository, task_id)[0]) == "BLOCKED"
    assert outcome["decision"]["decision"] == "ESCALATE"


def test_a_verifier_that_exhausts_the_runtime_budget_leaves_the_claim_blocked(
    repository: Any,
) -> None:
    task_id, session = claimed(
        repository,
        contract(verification=[spec("unit", [0], SLEEPS)], budget={**BUDGET, "max_runtime": 2}),
    )
    service.compile_plan(repository, task_id, phase="INITIAL")

    service.verify(repository, task_id, session)

    record = repository.store.list("evidence")[0]
    assert record["result"] == "BLOCKED"
    assert _status(repository, task_id, obligations_for(repository, task_id)[0]) == "BLOCKED"
    assert repository.store.get(task_id, "task")["state"] == "FAILED"


def test_a_run_interrupted_mid_flight_leaves_no_claim_verified(repository: Any) -> None:
    task_id, session = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    obligation = obligations_for(repository, task_id)[0]

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "agentic_discipline.control.verification.run_gate",
            lambda *args, **kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
        )
        with pytest.raises(KeyboardInterrupt):
            verify(repository, task_id, session)

    assert repository.store.list("evidence") == []
    assert _status(repository, task_id, obligation) == "UNRESOLVED"
    assert repository.store.get(task_id, "task")["active_run"] is None
    assert repository.store.audit()["status"] == "PASS"


def test_a_failed_database_write_leaves_no_half_compiled_plan(repository: Any) -> None:
    task_id, _ = claimed(repository, contract(risk="HIGH"))
    real = repository.store.put
    calls: list[str] = []

    def failing(kind: str, data: dict[str, Any], **kwargs: Any) -> Any:
        calls.append(kind)
        if kind == "obligation" and calls.count("obligation") == 2:
            raise sqlite3.OperationalError("disk I/O error")
        return real(kind, data, **kwargs)

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(repository.store, "put", failing)
        with pytest.raises(sqlite3.OperationalError):
            service.compile_plan(repository, task_id, phase="INITIAL")

    assert obligations_for(repository, task_id) == []
    assert [p for p in repository.store.list("assurance_plan") if p["task_id"] == task_id] == []
    assert repository.store.audit()["status"] == "PASS"


# --- what an agent might try -----------------------------------------------------------


def test_editing_the_tests_a_claim_rests_on_stops_it_being_proven(repository: Any) -> None:
    task_id, _, obligation = _verified(repository)

    (repository.root / "src" / "report_test.py").write_text("assert True  # weakened\n")

    assert _status(repository, task_id, obligation) == "STALE"


def test_a_later_pass_does_not_bury_a_current_failure(repository: Any) -> None:
    task_id, session = claimed(
        repository,
        contract(
            acceptance=["The value is one"],
            verification=[spec("unit", [0], FAILS), spec("acceptance", [0], PASSES)],
        ),
    )
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)

    status = _status(repository, task_id, obligations_for(repository, task_id)[0])

    assert status == "CONFLICTED"
    assert {e["result"] for e in repository.store.list("evidence")} == {"PASS", "FAIL"}


def test_changing_the_declared_verifiers_invalidates_the_proof_bound_to_them(
    repository: Any,
) -> None:
    task_id, _, obligation = _verified(repository)
    task = repository.store.get(task_id, "task")

    with repository.store.transaction():
        repository.store.put(
            "obligation",
            {**obligation, "required_verifiers": [digest({"kind": "unit", "command": ["x"]})]},
            expected=obligation["version"],
        )

    moved = repository.store.get(obligation["id"], "obligation")
    evidence = resolver.task_evidence(repository, task_id)
    assert resolver.resolve(repository, task, moved, evidence=evidence)["status"] == "UNRESOLVED"


def test_deleting_an_obligation_behind_the_engine_is_reported_by_the_integrity_check(
    repository: Any,
) -> None:
    task_id, _, obligation = _verified(repository)
    assert service.integrity(repository)["status"] == "PASS"

    with repository.store.transaction():
        repository.store.db.execute("DELETE FROM records WHERE id=?", (obligation["id"],))

    report = service.integrity(repository)
    assert report["status"] == "FAIL"
    assert report["findings"][0]["obligations"] == [obligation["id"]]
    assert "gone from the store" in report["findings"][0]["finding"]


def test_a_forged_obligation_status_is_reported_by_the_integrity_check(
    repository: Any,
) -> None:
    task_id, _, obligation = _verified(repository)

    with repository.store.transaction():
        repository.store.put(
            "obligation", {**obligation, "status": "VERIFIED"}, expected=obligation["version"]
        )

    report = service.integrity(repository)
    assert report["status"] == "FAIL"
    assert report["findings"][0]["finding"] == "persisted status VERIFIED is not an owner state"
    del task_id


def test_a_waiver_without_a_recorded_reason_is_reported(repository: Any) -> None:
    task_id, _, obligation = _verified(repository)

    with repository.store.transaction():
        repository.store.put(
            "obligation",
            {**obligation, "status": "WAIVED", "waiver_id": None},
            expected=obligation["version"],
        )

    report = service.integrity(repository)
    assert report["status"] == "FAIL"
    assert report["findings"][0]["finding"] == "waived without a recorded waiver"
    del task_id


def test_judgment_evidence_relabelled_as_deterministic_is_reported(repository: Any) -> None:
    task_id, session = claimed(
        repository,
        contract(acceptance=["The value is one"], verification=[spec("adversarial", [0])]),
    )
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    record = repository.store.list("evidence")[0]
    assert (record["evidence_class"], record["judgment"]) == (
        "AGENT_JUDGMENT",
        "NO_COUNTEREXAMPLE_FOUND",
    )

    with repository.store.transaction():
        repository.store.put(
            "evidence",
            {**record, "evidence_class": "DETERMINISTIC"},
            expected=record["version"],
        )

    report = service.integrity(repository)
    assert report["status"] == "FAIL"
    assert report["findings"][0]["finding"] == "judgment evidence declared as deterministic"


def test_a_completed_task_that_later_loses_its_proof_is_reported(repository: Any) -> None:
    task_id, session, obligation = _verified(repository)
    repository.checkpoint(task_id, session, {**_checkpoint()})
    assert complete(repository, task_id, session)["state"] == "COMPLETED"

    (repository.root / "src" / "report.py").write_text("value = 2\n")

    report = service.integrity(repository)
    assert report["status"] == "FAIL"
    finding = next(f for f in report["findings"] if f.get("task_id") == task_id)
    assert finding["finding"] == "completed while holding mandatory proof debt"
    assert finding["obligations"] == [obligation["id"]]


def _checkpoint() -> dict[str, Any]:
    from assurance_support import checkpoint

    return checkpoint()


# --- the completion invariant as a property -------------------------------------------


@pytest.mark.parametrize(
    ("commands", "completes"),
    [
        ([PASSES], True),
        ([FAILS], False),
        ([PASSES, FAILS], False),
        ([FAILS, PASSES], False),
        ([["no-such-verifier-binary"]], False),
    ],
)
def test_completion_happens_exactly_when_no_mandatory_claim_is_open(
    repository: Any, commands: list[list[str]], completes: bool
) -> None:
    task_id, session = claimed(
        repository,
        contract(
            acceptance=["The value is one"],
            verification=[
                spec(kind, [0], command)
                for kind, command in zip(("unit", "acceptance"), commands, strict=False)
            ],
        ),
    )
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    repository.checkpoint(task_id, session, _checkpoint())
    debt = service.status(repository, task_id)["tasks"][0]["proof_debt"]

    if completes:
        assert debt == 0
        assert complete(repository, task_id, session)["state"] == "COMPLETED"
    else:
        assert debt > 0
        with pytest.raises(ControlError):
            complete(repository, task_id, session)
        assert repository.store.get(task_id, "task")["state"] != "COMPLETED"
