"""The work and preflight operations of the versioned API hand on every argument they take.

The API validates its input against a schema and then calls `work` or `preflight`. A
misspelt key there would be silently read as absent, so each case replaces the operation
behind it and checks what arrives, both with every optional argument given and with none.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agentic_discipline.bootstrap import initialize_project
from agentic_discipline.common import run_git
from agentic_discipline.control import api, preflight, work
from agentic_discipline.control.plane import Plane


@pytest.fixture
def plane(tmp_path: Path) -> Any:
    root = tmp_path / "project"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='r'\n", encoding="utf-8")
    run_git(["init"], cwd=root)
    initialize_project(root)
    with Plane(root) as opened:
        yield opened


def _recording(monkeypatch: pytest.MonkeyPatch, owner: Any, name: str) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def operation(plane: Any, *args: Any, **options: Any) -> dict[str, Any]:
        calls.append({"args": list(args), **options})
        return {"status": "PASS"}

    monkeypatch.setattr(owner, name, operation)
    return calls


def test_work_start_hands_on_the_agent_its_capabilities_and_the_claim(
    plane: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _recording(monkeypatch, work, "start")

    api.call(plane, "work_start", {"request": "do it"}, local=True)
    api.call(
        plane,
        "work_start",
        {"request": "do it", "agent": "reviewer", "capabilities": ["testing"], "claim": False},
        local=True,
    )

    assert calls == [
        {"args": ["do it"], "agent": "local-agent", "capabilities": None, "claim": True},
        {"args": ["do it"], "agent": "reviewer", "capabilities": ["testing"], "claim": False},
    ]


def test_work_checkpoint_hands_on_its_summary_and_next_action(
    plane: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _recording(monkeypatch, work, "checkpoint")
    base = {"task_id": "TASK-1", "session": "token", "reason": "handoff"}

    api.call(plane, "work_checkpoint", base, local=True)
    api.call(
        plane,
        "work_checkpoint",
        {**base, "summary": ["half done"], "next_action": "write the tests"},
        local=True,
    )

    assert calls == [
        {"args": ["TASK-1", "token"], "reason": "handoff", "summary": None, "next_action": None},
        {
            "args": ["TASK-1", "token"],
            "reason": "handoff",
            "summary": ["half done"],
            "next_action": "write the tests",
        },
    ]


def test_work_finish_hands_on_its_summary(plane: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _recording(monkeypatch, work, "finish")
    base = {"task_id": "TASK-1", "session": "token"}

    api.call(plane, "work_finish", base, local=True)
    api.call(plane, "work_finish", {**base, "summary": ["done"]}, local=True)

    assert calls == [
        {"args": ["TASK-1", "token"], "summary": None},
        {"args": ["TASK-1", "token"], "summary": ["done"]},
    ]


def test_the_preflight_repairs_and_scans_unless_told_not_to(
    plane: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _recording(monkeypatch, preflight, "for_plane")

    api.call(plane, "preflight", {}, local=True)
    api.call(plane, "preflight", {"repair": False, "deep": False}, local=True)
    api.call(plane, "preflight", {"repair": False}, local=True)
    api.call(plane, "preflight", {"deep": False}, local=True)

    assert calls == [
        {"args": [], "repair_first": True, "deep": True},
        {"args": [], "repair_first": False, "deep": False},
        {"args": [], "repair_first": False, "deep": True},
        {"args": [], "repair_first": True, "deep": False},
    ]
