"""Shared setup for the assurance tests: real verifier processes, no stubbed verdicts."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from agentic_discipline.control.contracts import digest

# Real commands, so every recorded verdict comes from a process that actually ran.
PASSES = [sys.executable, "-c", "raise SystemExit(0)"]
FAILS = [sys.executable, "-c", "raise SystemExit(1)"]
# A command that cannot start at all, which is how a verifier reaches BLOCKED.
UNRUNNABLE = ["agentic-discipline-no-such-program", "--check"]

BUDGET = {
    "max_runtime": 120,
    "max_retries": 8,
    "max_files": 20,
    "max_lines": 4000,
    "max_external_calls": 0,
    "max_cost": 0,
}


def spec(kind: str, acceptance: list[int], command: list[str] | None = None) -> dict[str, Any]:
    return {"kind": kind, "command": list(command or PASSES), "acceptance": list(acceptance)}


def contract(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "objective": "Keep the reported value at one",
        "scope": ["src"],
        "out_of_scope": ["deployment"],
        "requirements": [],
        "acceptance": ["The reported value is one"],
        "dependencies": [],
        "boundaries": ["value API"],
        "context": [],
        "verification": [spec("unit", [0])],
        "required_evidence": ["unit"],
        "rollback": "Revert src",
        "definition_of_done": "Current proof and a checkpoint",
        "risk": "LOW",
        "budget": dict(BUDGET),
    }
    base.update(overrides)
    base["required_evidence"] = sorted({v["kind"] for v in base["verification"]})
    return base


def checkpoint(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "completed_work": ["implemented the slice"],
        "modified_files": ["src/report.py"],
        "commands_run": [],
        "tests_run": [],
        "test_results": [],
        "failures": [],
        "discoveries": [],
        "assumptions": [],
        "pending_issues": [],
        "current_hypothesis": "The declared verifiers establish the acceptance criteria",
        "next_action": "Verify, then finish",
    }
    base.update(overrides)
    return base


def sources(root: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def planned(plane: Any, data: dict[str, Any] | None = None) -> str:
    """Approve the declared commands and create a ready task, without taking a lease."""
    payload = data or contract()
    for verifier in payload["verification"]:
        plane.approve_command(verifier["command"])
    task = plane.create_task(payload)
    plane.ready(task["id"])
    return str(task["id"])


def claimed(plane: Any, data: dict[str, Any] | None = None) -> tuple[str, str]:
    """Approve the declared commands, create the task and take a lease on it."""
    payload = data or contract()
    for verifier in payload["verification"]:
        plane.approve_command(verifier["command"])
    task = plane.create_task(payload)
    plane.ready(task["id"])
    session = plane.join(f"worker-{task['id'][-6:]}", ["code"])["session"]
    plane.claim(task["id"], session)
    return task["id"], session


def by_claim(report: dict[str, Any], text: str) -> dict[str, Any]:
    matches = [o for o in report["obligations"] if text.lower() in o["claim"].lower()]
    assert len(matches) == 1, f"expected one obligation matching {text!r}, got {matches}"
    return matches[0]


def statuses(report: dict[str, Any]) -> dict[str, str]:
    return {o["id"]: o["status"] for o in report["obligations"]}


def policy_obligation(plane: Any, task_id: str, policy_id: str) -> dict[str, Any]:
    from agentic_discipline.control.assurance.resolver import obligations_for

    matches = [o for o in obligations_for(plane, task_id) if policy_id in o["origin"]["policy_ids"]]
    assert len(matches) == 1, f"expected one {policy_id} obligation, got {len(matches)}"
    return matches[0]


def verifier_digest(plane: Any, task_id: str, kind: str) -> str:
    task = plane.store.get(task_id, "task")
    return digest(next(v for v in task["verification"] if v["kind"] == kind))
