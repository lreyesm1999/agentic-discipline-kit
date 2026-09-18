"""Quality gate results, field by field.

`run_gate` is what every verification decision rests on. Existing tests checked the
status and exit code of a few outcomes, so a result could report the wrong command,
lose output, ignore the working directory or misreport a timeout unnoticed. Each
case compares the whole result.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline import quality
from agentic_discipline.quality import run_gate

LIMIT = 20_000


def _script(body: str) -> list[str]:
    return [sys.executable, "-c", body]


def _result(gate: dict[str, Any], cwd: Path) -> dict[str, Any]:
    result = asdict(run_gate(gate, cwd=cwd))
    duration = result.pop("duration_seconds")
    assert duration >= 0 and duration == round(duration, 3)
    return result


def test_passing_gate_reports_its_output_from_the_working_directory(tmp_path: Path) -> None:
    command = _script("import os, sys; print(os.getcwd()); print('warn', file=sys.stderr)")
    assert _result({"name": "where", "command": command}, tmp_path) == {
        "name": "where",
        "required": True,
        "command": command,
        "exit_code": 0,
        "status": "PASS",
        "metrics": {},
        "threshold_failures": [],
        "stdout": f"{tmp_path}\n",
        "stderr": "warn\n",
        "error": None,
    }


def test_metrics_are_read_from_stdout_and_stderr_as_separate_lines(tmp_path: Path) -> None:
    command = _script("import sys; sys.stdout.write('A=1'); sys.stderr.write('B=2')")
    gate = {
        "name": "metrics",
        "command": command,
        "required": False,
        "parser": {"type": "regex", "metrics": {"a": r"^A=(\d+)$", "b": r"^B=(\d+)$"}},
        "thresholds": {"a": {"min": 1}, "b": {"max": 1}},
    }
    assert _result(gate, tmp_path) == {
        "name": "metrics",
        "required": False,
        "command": command,
        "exit_code": 0,
        "status": "FAIL",
        "metrics": {"a": 1.0, "b": 2.0},
        "threshold_failures": ["b 2.0 > 1"],
        "stdout": "A=1",
        "stderr": "B=2",
        "error": None,
    }


def test_failing_exit_code_fails_without_thresholds(tmp_path: Path) -> None:
    result = _result({"name": "exit", "command": _script("raise SystemExit(3)")}, tmp_path)
    assert (result["exit_code"], result["status"], result["error"]) == (3, "FAIL", None)


def test_output_keeps_only_its_last_characters(tmp_path: Path) -> None:
    body = (
        "import sys; sys.stdout.write('x' * 20000 + 'END'); sys.stderr.write('y' * 20000 + 'ERR')"
    )
    result = _result({"name": "long", "command": _script(body)}, tmp_path)
    assert result["stdout"] == ("x" * 20000 + "END")[-LIMIT:]
    assert result["stderr"] == ("y" * 20000 + "ERR")[-LIMIT:]


def test_missing_executable_is_an_error_result(tmp_path: Path) -> None:
    command = ["definitely-not-an-adk-command", "--flag"]
    result = _result({"name": "missing", "command": command, "required": False}, tmp_path)
    error = result.pop("error")
    assert error and isinstance(error, str)
    assert result == {
        "name": "missing",
        "required": False,
        "command": command,
        "exit_code": 127,
        "status": "ERROR",
        "metrics": {},
        "threshold_failures": [],
        "stdout": "",
        "stderr": "",
    }


def test_real_timeout_is_an_error_result(tmp_path: Path) -> None:
    command = _script("import time; print('started', flush=True); time.sleep(30)")
    gate = {
        "name": "slow",
        "command": command,
        "timeout_seconds": 1,
        "parser": {"type": "regex", "metrics": {"x": r"(started)"}},
    }
    result = _result(gate, tmp_path)
    output = result.pop("stdout")
    assert result == {
        "name": "slow",
        "required": True,
        "command": command,
        "exit_code": 124,
        "status": "ERROR",
        "metrics": {},
        "threshold_failures": [],
        "stderr": "",
        "error": "gate timed out after 1 seconds",
    }
    assert output in {"", "started\n", "started\r\n"}


class _Run:
    def __init__(self, outcome: Any) -> None:
        self.outcome = outcome
        self.calls: list[tuple[Any, dict[str, Any]]] = []

    def __call__(self, command: Any, **options: Any) -> Any:
        self.calls.append((command, options))
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def test_string_commands_are_split_and_run_without_a_shell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _Run(subprocess.CompletedProcess([], 0, "", ""))
    monkeypatch.setattr(quality.subprocess, "run", fake)

    result = run_gate({"name": "split", "command": 'tool "two words" --x'}, cwd=tmp_path)

    assert (result.command, result.status) == ('tool "two words" --x', "PASS")
    assert fake.calls == [
        (
            ["tool", "two words", "--x"],
            {
                "cwd": tmp_path,
                "shell": False,
                "encoding": "utf-8",
                "errors": "replace",
                "capture_output": True,
                "check": False,
                "timeout": 900.0,
            },
        )
    ]


def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    ticks = iter([10.0, 11.23456])
    monkeypatch.setattr(quality.time, "monotonic", lambda: next(ticks))


@pytest.mark.parametrize(
    ("stdout", "stderr", "expected_stdout", "expected_stderr"),
    [
        (None, None, "", ""),
        (b"\xffok", b"\xfeerr", "�ok", "�err"),
        ("x" * 20000 + "END", "y" * 20000 + "ERR", "x" * 19997 + "END", "y" * 19997 + "ERR"),
    ],
    ids=["missing", "bytes", "long"],
)
def test_timeout_result_decodes_trims_and_reports_the_default_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stdout: Any,
    stderr: Any,
    expected_stdout: str,
    expected_stderr: str,
) -> None:
    expired = subprocess.TimeoutExpired(["tool"], 900, output=stdout, stderr=stderr)
    monkeypatch.setattr(quality.subprocess, "run", _Run(expired))
    _clock(monkeypatch)

    result = run_gate({"name": "slow", "command": ["tool"]}, cwd=tmp_path)

    assert asdict(result) == {
        "name": "slow",
        "required": True,
        "command": ["tool"],
        "exit_code": 124,
        "status": "ERROR",
        "duration_seconds": 1.235,
        "metrics": {},
        "threshold_failures": [],
        "stdout": expected_stdout,
        "stderr": expected_stderr,
        "error": "gate timed out after 900 seconds",
    }


@pytest.mark.parametrize("required", [True, False])
def test_timeout_and_missing_executable_keep_the_required_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, required: bool
) -> None:
    gate = {"name": "gate", "command": ["tool"], "required": required}
    for outcome in (subprocess.TimeoutExpired(["tool"], 1), FileNotFoundError("no tool")):
        monkeypatch.setattr(quality.subprocess, "run", _Run(outcome))
        _clock(monkeypatch)
        result = run_gate(gate, cwd=tmp_path)
        assert (result.required, result.duration_seconds) == (required, 1.235)


def test_missing_executable_is_required_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(quality.subprocess, "run", _Run(FileNotFoundError("no tool")))
    _clock(monkeypatch)
    assert asdict(run_gate({"name": "gate", "command": ["tool"]}, cwd=tmp_path)) == {
        "name": "gate",
        "required": True,
        "command": ["tool"],
        "exit_code": 127,
        "status": "ERROR",
        "duration_seconds": 1.235,
        "metrics": {},
        "threshold_failures": [],
        "stdout": "",
        "stderr": "",
        "error": "no tool",
    }
