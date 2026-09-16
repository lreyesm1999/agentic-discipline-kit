"""Which run of a verifier the context reports as a current failure.

`context` keeps one evidence record per verifier, the one that finished last, so a
repaired run replaces the failure an agent would otherwise be told to fix. Records
are listed by identifier and identifiers are random, so a comparison that reads the
wrong field still looks right whenever list order happens to match time order, and
a scan that stops early still looks right whenever the failure happens to come
first. Each case fixes the identifiers and the timestamps so the two disagree.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from conftest import contract

UNIT = "verifier-unit"
LINT = "verifier-lint"


def _evidence(
    project: Any, identifier: str, task_id: str, verifier: str, result: str, finished_at: float
) -> dict[str, Any]:
    """Write an evidence record and the artifact the context reads back."""
    artifact = project.directory / "evidence" / (identifier + ".json")
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps({"result": result}), encoding="utf-8")
    record = {
        "id": identifier,
        "task_id": task_id,
        "kind": "unit",
        "verifier": verifier,
        "acceptance": [0],
        "run_id": "RUN-1",
        "result": result,
        "exit_code": 0 if result == "PASS" else 1,
        "command": ["python", "test_app.py"],
        "binding": {},
        "knowledge_version": project.store.knowledge_version,
        "artifact_hash": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "artifact_ref": f".agentic/control/evidence/{identifier}.json",
        "started_at": finished_at - 1,
        "finished_at": finished_at,
        "stale": False,
    }
    with project.store.transaction():
        return project.store.put("evidence", record)


def _task(project: Any) -> str:
    project.approve_command(contract()["verification"][0]["command"])
    return str(project.create_task(contract())["id"])


def _failures(project: Any, task_id: str) -> list[str]:
    context = project.context(task_id, budget=1_000_000)
    return [item["evidence"]["id"] for item in context["mandatory"]["current_failures"]]


def test_the_run_that_finished_last_is_the_one_reported(project: Any) -> None:
    # EVD-1 is listed first but finished last, so listing order is not time order.
    task = _task(project)
    _evidence(project, "EVD-1", task, UNIT, "FAIL", 2000.0)
    _evidence(project, "EVD-2", task, UNIT, "PASS", 1000.0)

    assert _failures(project, task) == ["EVD-1"]


def test_a_repaired_run_clears_the_earlier_failure(project: Any) -> None:
    task = _task(project)
    _evidence(project, "EVD-1", task, UNIT, "FAIL", 1000.0)
    _evidence(project, "EVD-2", task, UNIT, "PASS", 2000.0)

    assert _failures(project, task) == []


def test_a_passing_verifier_does_not_hide_another_that_failed(project: Any) -> None:
    # The passing record is scanned first; the failure behind it must still be read.
    task = _task(project)
    _evidence(project, "EVD-1", task, LINT, "PASS", 1000.0)
    _evidence(project, "EVD-2", task, UNIT, "FAIL", 1000.0)

    assert _failures(project, task) == ["EVD-2"]


def test_evidence_of_another_task_is_not_reported(project: Any) -> None:
    task, other = _task(project), _task(project)
    _evidence(project, "EVD-1", other, UNIT, "FAIL", 2000.0)

    assert _failures(project, task) == []
