"""`agentic work` and `agentic preflight`, run through `main()` with what they hand on.

The command line adds nothing to the work: it checks what it was given, runs the preflight,
and passes its options to `work`. So each case here replaces the operation behind it, and
checks that every option arrives, that each refusal is worded exactly, and that the answer
comes back in the versioned envelope.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline.bootstrap import initialize_project
from agentic_discipline.common import run_git
from agentic_discipline.control import cli, preflight, work
from agentic_discipline.control.plane import Plane

REQUEST = "Add a total to src/app.py"
FULL = {"mode": "FULL", "reason": "ready", "requirements": [], "status": "PASS"}


@pytest.fixture
def root(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    (project / "src").mkdir(parents=True)
    (project / "pyproject.toml").write_text("[project]\nname='r'\n", encoding="utf-8")
    (project / "src" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    run_git(["init"], cwd=project)
    initialize_project(project)
    with Plane(project) as plane:
        plane.reconcile()
    return project


def _main(monkeypatch: pytest.MonkeyPatch, capsys: Any, *argv: str) -> tuple[int, Any]:
    monkeypatch.setattr(sys, "argv", ["agentic", *argv])
    capsys.readouterr()
    try:
        cli.main()
        code = 0
    except SystemExit as exit_:
        code = int(exit_.code or 0)
    out = capsys.readouterr().out
    try:
        return code, json.loads(out)
    except ValueError:
        return code, out


def _flight(monkeypatch: pytest.MonkeyPatch, result: dict[str, Any]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def run(root: Path, **options: Any) -> dict[str, Any]:
        calls.append(options)
        return dict(result)

    monkeypatch.setattr(preflight, "run", run)
    return calls


def _recording(monkeypatch: pytest.MonkeyPatch, name: str, answer: Any) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def operation(plane: Any, *args: Any, **options: Any) -> Any:
        calls.append({"args": list(args), **options})
        return answer

    monkeypatch.setattr(work, name, operation)
    return calls


def _error(code: str, message: str) -> dict[str, str]:
    return {"api_version": "2", "status": "ERROR", "code": code, "message": message}


# --- start and derive ----------------------------------------------------------------------


@pytest.mark.parametrize("action", ["start", "derive"])
def test_a_request_with_no_words_is_refused(
    root: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any, action: str
) -> None:
    assert _main(monkeypatch, capsys, "--root", str(root), "work", action, "  ") == (
        2,
        _error("INVALID_REQUEST", "Describe the work"),
    )


def test_a_blocked_preflight_is_the_answer(
    root: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    blocked = {"mode": "BLOCKED", "reason": "history altered", "requirements": []}
    _flight(monkeypatch, blocked)

    code, answer = _main(monkeypatch, capsys, "--root", str(root), "work", "start", "x", "--json")

    assert (code, answer) == (2, {"api_version": "2", "data": {**blocked, "status": "BLOCKED"}})


def test_derive_answers_with_the_derivation_alone(
    root: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    _flight(monkeypatch, FULL)
    code, answer = _main(
        monkeypatch, capsys, "--root", str(root), "work", "derive", REQUEST, "--json"
    )

    with Plane(root) as plane:
        expected = work.derive(plane, REQUEST)
    assert (code, answer) == (0, {"api_version": "2", "data": expected})


def test_start_hands_every_option_to_the_work_and_writes_the_session(
    root: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any, tmp_path: Path
) -> None:
    _flight(monkeypatch, FULL)
    calls = _recording(monkeypatch, "start", {"status": "PASS", "session": "the-token"})
    session_out = tmp_path / "outside" / "nested" / "session.json"

    code, answer = _main(
        monkeypatch,
        capsys,
        "--root",
        str(root),
        "work",
        "start",
        REQUEST,
        "--agent",
        "reviewer",
        "--capability",
        "code",
        "--capability",
        "testing",
        "--no-claim",
        "--session-out",
        str(session_out),
        "--json",
    )

    assert (code, answer) == (
        0,
        {"api_version": "2", "data": {"status": "PASS", "session": "the-token"}},
    )
    assert calls == [
        {
            "args": [REQUEST],
            "agent": "reviewer",
            "capabilities": ["code", "testing"],
            "claim": False,
            "flight": FULL,
        }
    ]
    assert session_out.read_bytes() == b'{"session": "the-token"}\n'
    if os.name == "posix":
        assert session_out.stat().st_mode & 0o777 == 0o600


def test_start_claims_by_default_and_writes_no_session_it_was_not_given(
    root: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any, tmp_path: Path
) -> None:
    _flight(monkeypatch, FULL)
    calls = _recording(monkeypatch, "start", {"status": "PASS", "session": None})
    session_out = tmp_path / "session.json"

    _main(
        monkeypatch,
        capsys,
        "--root",
        str(root),
        "work",
        "start",
        REQUEST,
        "--session-out",
        str(session_out),
        "--json",
    )

    assert (calls[0]["agent"], calls[0]["capabilities"], calls[0]["claim"]) == (
        "local-agent",
        [],
        True,
    )
    assert not session_out.exists()


# --- the preflight command -----------------------------------------------------------------


def test_the_preflight_command_passes_its_options_and_answers_in_the_envelope(
    root: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    calls = _flight(monkeypatch, FULL)

    first = _main(monkeypatch, capsys, "--root", str(root), "preflight", "--json")
    second = _main(
        monkeypatch, capsys, "--root", str(root), "preflight", "--no-repair", "--fast", "--json"
    )

    assert first == second == (0, {"api_version": "2", "data": FULL})
    assert calls == [
        {"repair_first": True, "deep": True},
        {"repair_first": False, "deep": False},
    ]


# --- verify, finish and checkpoint ---------------------------------------------------------


@pytest.fixture
def session_file(tmp_path: Path) -> Path:
    path = tmp_path / "sessions" / "agent.json"
    cli.write_session(path, "the-token")
    return path


@pytest.mark.parametrize("action", ["verify", "finish", "checkpoint"])
def test_each_task_operation_needs_its_task(
    root: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any, action: str, session_file: Path
) -> None:
    code, answer = _main(
        monkeypatch,
        capsys,
        "--root",
        str(root),
        "work",
        action,
        "--session-file",
        str(session_file),
    )

    assert (code, answer) == (2, _error("TASK_REQUIRED", "Name the task with --task"))


def test_verify_finish_and_checkpoint_each_reach_their_own_operation(
    root: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any, session_file: Path
) -> None:
    verified = _recording(monkeypatch, "verify", {"status": "PASS", "step": "verify"})
    finished = _recording(monkeypatch, "finish", {"status": "PASS", "step": "finish"})
    marked = _recording(monkeypatch, "checkpoint", {"status": "PASS", "step": "checkpoint"})
    common = ["--root", str(root), "work"]
    task = ["--task", "TASK-1", "--session-file", str(session_file), "--json"]

    answers = [
        _main(monkeypatch, capsys, *common, "verify", *task),
        _main(monkeypatch, capsys, *common, "finish", *task, "--summary", "added it"),
        _main(
            monkeypatch,
            capsys,
            *common,
            "checkpoint",
            *task,
            "--reason",
            "handoff",
            "--summary",
            "half done",
            "--summary",
            "tests next",
            "--next-action",
            "write the tests",
        ),
    ]

    assert [answer["data"]["step"] for _, answer in answers] == ["verify", "finish", "checkpoint"]
    assert verified == [{"args": ["TASK-1", "the-token"]}]
    assert finished == [{"args": ["TASK-1", "the-token"], "summary": ["added it"]}]
    assert marked == [
        {
            "args": ["TASK-1", "the-token"],
            "reason": "handoff",
            "summary": ["half done", "tests next"],
            "next_action": "write the tests",
        }
    ]
