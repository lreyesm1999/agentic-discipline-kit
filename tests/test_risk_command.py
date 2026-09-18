"""`agentic-discipline risk` command decisions.

The risk command chooses which weights apply, asks git for the exact diff and turns
the assessed level into an exit code CI can gate on. The existing test only checked
a pass and a git failure, so a weights file could be ignored, the wrong one could
win, or `--fail-at` could stop failing unnoticed. Each case records what the command
reads and returns.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from agentic_discipline import cli
from agentic_discipline.common import AgenticError


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    seen: dict[str, Any] = {"git": [], "files": [], "weights": [], "assess": [], "json": []}
    monkeypatch.chdir(tmp_path)

    def changed_files(ref: str) -> list[str]:
        seen["files"].append(ref)
        return ["src/payment.py"]

    def run_git(arguments: list[str]) -> str:
        seen["git"].append(arguments)
        return "+balance = 1"

    def load_weights(path: Path) -> dict[str, int]:
        seen["weights"].append(path)
        return {"payment": 9}

    def with_weights(diff: str, files: list[str], weights: dict[str, int]) -> Any:
        seen["assess"].append(("weighted", diff, files, weights))
        return seen["result"]

    def default(diff: str, files: list[str]) -> Any:
        seen["assess"].append(("default", diff, files))
        return seen["result"]

    seen["result"] = SimpleNamespace(level="HIGH")
    monkeypatch.setattr(cli, "changed_files", changed_files)
    monkeypatch.setattr(cli, "run_git", run_git)
    monkeypatch.setattr(cli, "load_risk_weights", load_weights)
    monkeypatch.setattr(cli, "assess_risk_with_weights", with_weights)
    monkeypatch.setattr(cli, "assess_risk", default)
    monkeypatch.setattr(cli, "_json", lambda value: seen["json"].append(value))
    return seen


def _args(**values: Any) -> argparse.Namespace:
    return argparse.Namespace(base_ref="origin/main", **values)


def _config(relative: str) -> Path:
    path = Path(relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    return path


def test_without_weights_the_default_assessment_is_printed(recorded: dict[str, Any]) -> None:
    assert cli.command_risk(_args()) == 0
    assert recorded["files"] == ["origin/main"]
    assert recorded["git"] == [["diff", "--unified=0", "origin/main", "--"]]
    assert recorded["weights"] == []
    assert recorded["assess"] == [("default", "+balance = 1", ["src/payment.py"])]
    assert recorded["json"] == [recorded["result"]]


def test_installed_payload_weights_win_over_the_legacy_location(recorded: dict[str, Any]) -> None:
    _config("config/risk-weights.json")
    _config(".agentic/config/risk-weights.json")
    assert cli.command_risk(_args()) == 0
    assert recorded["weights"] == [Path(".agentic/config/risk-weights.json")]
    assert recorded["assess"] == [("weighted", "+balance = 1", ["src/payment.py"], {"payment": 9})]


def test_legacy_weights_are_used_when_the_payload_has_none(recorded: dict[str, Any]) -> None:
    _config("config/risk-weights.json")
    cli.command_risk(_args())
    assert recorded["weights"] == [Path("config/risk-weights.json")]


def test_a_directory_named_like_the_weights_file_is_ignored(recorded: dict[str, Any]) -> None:
    Path(".agentic/config/risk-weights.json").mkdir(parents=True)
    cli.command_risk(_args())
    assert recorded["weights"] == []
    assert recorded["assess"][0][0] == "default"


def test_explicit_weights_skip_discovery(recorded: dict[str, Any], tmp_path: Path) -> None:
    _config(".agentic/config/risk-weights.json")
    explicit = tmp_path / "custom.json"
    cli.command_risk(_args(weights=str(explicit)))
    assert recorded["weights"] == [explicit]


@pytest.mark.parametrize(
    ("fail_at", "code"),
    [(None, 0), ("", 0), ("LOW", 1), ("HIGH", 1), ("CRITICAL", 0)],
)
def test_fail_at_turns_the_level_into_an_exit_code(
    recorded: dict[str, Any], fail_at: str | None, code: int
) -> None:
    assert cli.command_risk(_args(fail_at=fail_at)) == code
    assert recorded["json"] == [recorded["result"]]


@pytest.mark.parametrize("broken", ["changed_files", "run_git"])
def test_git_errors_are_reported_on_stderr_with_exit_2(
    recorded: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    broken: str,
) -> None:
    def fail(*_: Any) -> Any:
        raise AgenticError("git is unavailable")

    monkeypatch.setattr(cli, broken, fail)
    assert cli.command_risk(_args(fail_at="LOW")) == 2
    assert capsys.readouterr().err == "git is unavailable\n"
    assert (recorded["assess"], recorded["json"]) == ([], [])
