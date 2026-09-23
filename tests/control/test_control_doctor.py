"""Control-plane doctor result, field by field.

`doctor` combines the installation diagnostics of the project with the audit chain of
its control state. The existing test only saw a real passing run, so the diagnostic
command, its timeout or the rule that both halves must pass could change unnoticed.
The subprocess is recorded so each case pins exactly what doctor runs and reports.
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

import pytest
from conftest import contract

from agentic_discipline.control import diagnostics
from agentic_discipline.control.assurance.service import integrity
from agentic_discipline.control.diagnostics import doctor


@pytest.fixture
def installation(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"calls": [], "code": 0, "report": {"status": "PASS", "checks": []}}

    def run(command: list[str], **options: Any) -> subprocess.CompletedProcess[str]:
        state["calls"].append((command, options))
        return subprocess.CompletedProcess(command, state["code"], json.dumps(state["report"]), "")

    monkeypatch.setattr(diagnostics.subprocess, "run", run)
    return state


def test_doctor_runs_the_installation_check_in_the_project(
    project: Any, installation: dict[str, Any]
) -> None:
    project.join("worker", ["code"])
    audit = project.store.audit()

    assert doctor(project) == {
        "status": "PASS",
        "installation": {"status": "PASS", "checks": []},
        "control_audit": audit,
        "assurance_integrity": integrity(project),
    }
    assert installation["calls"] == [
        (
            [sys.executable, "-m", "agentic_discipline", "doctor"],
            {
                "cwd": project.root,
                "text": True,
                "capture_output": True,
                "check": False,
                "timeout": 30,
            },
        )
    ]


def test_a_failing_installation_check_fails_doctor(
    project: Any, installation: dict[str, Any]
) -> None:
    project.join("worker", ["code"])
    installation["code"] = 1
    installation["report"] = {"status": "FAIL", "checks": ["missing tool"]}
    result = doctor(project)
    assert (result["status"], result["installation"]) == (
        "FAIL",
        {"status": "FAIL", "checks": ["missing tool"]},
    )


def test_an_unknown_audit_fails_doctor_even_when_installation_passes(
    tmp_path: Any, installation: dict[str, Any]
) -> None:
    from agentic_discipline.control.plane import Plane, adopt

    adopt(tmp_path)
    with Plane(tmp_path) as plane:
        with plane.store.transaction():
            plane.store.db.execute("DROP TRIGGER events_no_delete")
        plane.store.db.execute("DELETE FROM events")
        assert plane.store.audit()["status"] == "UNKNOWN"
        assert doctor(plane)["status"] == "FAIL"


def test_a_broken_assurance_invariant_fails_doctor(
    project: Any, installation: dict[str, Any]
) -> None:
    """Project health includes the assurance invariants, not only the audit chain."""
    from agentic_discipline.control.assurance import service

    declared = contract()
    project.approve_command(declared["verification"][0]["command"])
    task = project.create_task(declared)
    project.ready(task["id"])
    service.compile_plan(project, task["id"], phase="INITIAL")
    obligation = service.obligations_for(project, task["id"])[0]
    with project.store.transaction():
        project.store.put(
            "obligation", {**obligation, "status": "VERIFIED"}, expected=obligation["version"]
        )

    result = doctor(project)

    assert result["status"] == "FAIL"
    assert result["installation"] == {"status": "PASS", "checks": []}
    assert result["control_audit"]["status"] == "PASS"
    assert result["assurance_integrity"]["status"] == "FAIL"
