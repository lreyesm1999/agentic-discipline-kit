"""Control-plane CLI entry point: printing, exit codes and error envelopes.

`main` is what shells and CI actually invoke. Existing tests ran it for one status
and one error, so the human status summary, the exit code for a failing or blocked
result, or the error envelope printed for a crash could change unnoticed. The command
itself is recorded so each case pins exactly what `main` prints and how it exits.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline.control import cli
from agentic_discipline.control.contracts import ControlError, encode


def _main(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, outcome: Any, *arguments: str) -> None:
    def run(args: Any) -> Any:
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(cli, "run", run)
    monkeypatch.setattr(sys, "argv", ["agentic", "--root", str(tmp_path), *arguments])
    cli.main()


STATUS = {
    "api_version": "2",
    "data": {
        "project": {"name": "demo"},
        "knowledge_version": 7,
        "task_counts": {"READY": 2, "BLOCKED": 1},
        "knowledge": {"stale": 3},
        "audit": {"status": "PASS"},
    },
}


def test_json_output_is_the_encoded_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _main(monkeypatch, tmp_path, STATUS, "status", "--json")
    assert capsys.readouterr().out == encode(STATUS) + "\n"


def test_human_status_is_a_short_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _main(monkeypatch, tmp_path, STATUS, "status")
    assert capsys.readouterr().out.splitlines() == [
        "Project: demo",
        "Knowledge revision: 7",
        "READY: 2",
        "BLOCKED: 1",
        "Stale knowledge: 3",
        "Audit: PASS",
    ]


def test_other_human_output_is_indented_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = {"api_version": "2", "data": {"status": "PASS", "items": [1]}}
    _main(monkeypatch, tmp_path, result, "doctor")
    assert capsys.readouterr().out == json.dumps(result, indent=2) + "\n"


@pytest.mark.parametrize(("status", "code"), [("FAIL", 1), ("BLOCKED", 2), ("ERROR", 2)])
def test_unsuccessful_results_exit_with_their_code(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    status: str,
    code: int,
) -> None:
    result = {"data": {"status": status}}
    with pytest.raises(SystemExit) as raised:
        _main(monkeypatch, tmp_path, result, "doctor", "--json")
    assert raised.value.code == code
    assert capsys.readouterr().out == encode(result) + "\n"


@pytest.mark.parametrize(
    "result",
    [
        None,
        {"data": {"status": "PASS"}},
        {"data": {"status": "READY"}},
        {"data": [{"status": "FAIL"}]},
        {"api_version": "2"},
    ],
)
def test_successful_or_non_status_results_do_not_exit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    result: Any,
) -> None:
    _main(monkeypatch, tmp_path, result, "doctor", "--json")
    assert capsys.readouterr().out == ("" if result is None else encode(result) + "\n")


@pytest.mark.parametrize(
    ("error", "code", "message"),
    [
        (
            ControlError("NOT_FOUND", "Record not found: TASK-1"),
            "NOT_FOUND",
            "Record not found: TASK-1",
        ),
        (OSError("disk full"), "OPERATION_FAILED", "disk full"),
        (ValueError("bad value"), "OPERATION_FAILED", "bad value"),
        (KeyError("task_id"), "OPERATION_FAILED", "'task_id'"),
        (TypeError("wrong type"), "OPERATION_FAILED", "wrong type"),
        (sqlite3.OperationalError("database is locked"), "OPERATION_FAILED", "database is locked"),
    ],
)
def test_expected_errors_print_an_envelope_and_exit_2(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
    code: str,
    message: str,
) -> None:
    with pytest.raises(SystemExit) as raised:
        _main(monkeypatch, tmp_path, error, "status")
    assert raised.value.code == 2
    assert raised.value.__cause__ is error
    assert (
        capsys.readouterr().out
        == encode({"api_version": "2", "status": "ERROR", "code": code, "message": message}) + "\n"
    )


def test_unexpected_errors_are_not_swallowed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(RuntimeError, match="bug"):
        _main(monkeypatch, tmp_path, RuntimeError("bug"), "status")
    assert capsys.readouterr().out == ""
