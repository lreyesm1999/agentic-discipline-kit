"""The ``doctor`` report, field by field and variant by variant.

``agentic-discipline doctor`` is the installation health check that users and CI
run first. Existing tests only checked its exit code, so a field could report the
wrong value, a fallback could stop working, or a required tool could be ignored
while the status still said PASS. Every case runs doctor on a real project and
compares the whole JSON report.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline import __version__, cli
from agentic_discipline.bootstrap import initialize_project
from agentic_discipline.common import AgenticError, run_git
from agentic_discipline.validation import load_quality_config


@pytest.fixture
def installed(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    initialize_project(root)
    run_git(["init"], cwd=root)
    return root


def _doctor(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], root: Path, **args: Any
) -> tuple[int, dict[str, Any]]:
    monkeypatch.chdir(root)
    capsys.readouterr()
    code = cli.command_doctor(argparse.Namespace(**args))
    return code, json.loads(capsys.readouterr().out)


def _skills(root: Path) -> int:
    return len(list((root / ".agentic" / "skills").glob("*/SKILL.md")))


def _report(root: Path, **changes: Any) -> dict[str, Any]:
    report: dict[str, Any] = {
        "python": sys.version.split()[0],
        "git": shutil.which("git") is not None,
        "git_worktree": True,
        "package_version": __version__,
        "agents_md": True,
        "master_prompt": True,
        "config": True,
        "config_schema": True,
        "config_path": str(root.resolve() / "agentic.config.json"),
        "config_valid": True,
        "config_error": None,
        "tools": {},
        "skills": _skills(root),
        "status": "PASS",
    }
    report.update(changes)
    return report


def _write_gates(path: Path, gates: list[tuple[Any, bool | None]]) -> None:
    """Write gates; ``None`` omits ``required`` so the default applies."""
    config = json.loads(path.read_text(encoding="utf-8"))
    template = {k: v for k, v in config["gates"][0].items() if k != "required"}
    config["gates"] = [
        {
            **template,
            "name": f"gate-{index}",
            "command": command,
            **({} if required is None else {"required": required}),
        }
        for index, (command, required) in enumerate(gates)
    ]
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")


def test_gate_without_required_flag_counts_as_required(
    monkeypatch: Any, capsys: Any, installed: Path
) -> None:
    _write_gates(installed / "agentic.config.json", [(["adk-missing-default-tool"], None)])
    code, report = _doctor(monkeypatch, capsys, installed, check_tools=True)
    expected = _report(installed, tools={"adk-missing-default-tool": False}, status="FAIL")
    assert (code, report) == (1, expected)


def test_healthy_installation_passes(monkeypatch: Any, capsys: Any, installed: Path) -> None:
    assert _skills(installed) >= cli.EXPECTED_DISCIPLINES
    assert _doctor(monkeypatch, capsys, installed) == (0, _report(installed))


def test_required_missing_tools_fail_but_relaxed_ones_do_not(
    monkeypatch: Any, capsys: Any, installed: Path
) -> None:
    config = installed / "agentic.config.json"
    _write_gates(
        config,
        [
            ([sys.executable, "-V"], True),
            (["adk-missing-required-tool"], True),
            ("adk-missing-text-tool --flag", True),
            (["adk-missing-relaxed-tool"], False),
        ],
    )
    tools = {
        sys.executable: True,
        "adk-missing-required-tool": False,
        "adk-missing-text-tool": False,
        "adk-missing-relaxed-tool": False,
    }
    code, report = _doctor(monkeypatch, capsys, installed, check_tools=True)
    assert (code, report) == (1, _report(installed, tools=tools, status="FAIL"))

    _write_gates(config, [([sys.executable, "-V"], True), (["adk-missing-relaxed-tool"], False)])
    code, report = _doctor(monkeypatch, capsys, installed, check_tools=True)
    relaxed = {sys.executable: True, "adk-missing-relaxed-tool": False}
    assert (code, report) == (0, _report(installed, tools=relaxed))

    # Without --check-tools nothing is probed, even though a required tool is missing.
    _write_gates(config, [(["adk-missing-required-tool"], True)])
    assert _doctor(monkeypatch, capsys, installed) == (0, _report(installed))


def test_example_config_is_the_fallback(monkeypatch: Any, capsys: Any, installed: Path) -> None:
    config = installed / "agentic.config.json"
    example = installed / "agentic.config.example.json"
    example.write_text(config.read_text(encoding="utf-8"), encoding="utf-8")
    config.unlink()
    expected = _report(installed, config_path=str(installed.resolve() / example.name))
    assert _doctor(monkeypatch, capsys, installed) == (0, expected)


def test_missing_config_fails(monkeypatch: Any, capsys: Any, installed: Path) -> None:
    (installed / "agentic.config.json").unlink()
    expected = _report(installed, config=False, config_path=None, config_valid=False, status="FAIL")
    assert _doctor(monkeypatch, capsys, installed) == (1, expected)


def test_invalid_config_reports_its_error(monkeypatch: Any, capsys: Any, installed: Path) -> None:
    config = installed / "agentic.config.json"
    config.write_text("{not json", encoding="utf-8")
    with pytest.raises(AgenticError) as caught:
        load_quality_config(config)
    expected = _report(installed, config_valid=False, config_error=str(caught.value), status="FAIL")
    assert _doctor(monkeypatch, capsys, installed) == (1, expected)


def test_explicit_config_argument_wins(
    monkeypatch: Any, capsys: Any, installed: Path, tmp_path: Path
) -> None:
    elsewhere = tmp_path / "custom.json"
    elsewhere.write_text(
        (installed / "agentic.config.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (installed / "agentic.config.json").write_text("{not json", encoding="utf-8")
    expected = _report(installed, config_path=str(elsewhere))
    assert _doctor(monkeypatch, capsys, installed, config=str(elsewhere)) == (0, expected)


def test_outside_a_git_worktree_fails(monkeypatch: Any, capsys: Any, tmp_path: Path) -> None:
    root = tmp_path / "plain"
    root.mkdir()
    initialize_project(root)
    expected = _report(root, git_worktree=False, status="FAIL")
    assert _doctor(monkeypatch, capsys, root) == (1, expected)


def test_missing_git_is_reported(monkeypatch: Any, capsys: Any, installed: Path) -> None:
    real_which = shutil.which
    monkeypatch.setattr(
        cli.shutil, "which", lambda name, *a, **k: None if name == "git" else real_which(name)
    )
    expected = _report(installed, git=False, git_worktree=False, status="FAIL")
    assert _doctor(monkeypatch, capsys, installed) == (1, expected)


def test_discipline_count_boundary(monkeypatch: Any, capsys: Any, installed: Path) -> None:
    skills = sorted((installed / ".agentic" / "skills").glob("*/SKILL.md"))
    for extra in skills[cli.EXPECTED_DISCIPLINES :]:
        extra.unlink()
    assert _skills(installed) == cli.EXPECTED_DISCIPLINES
    assert _doctor(monkeypatch, capsys, installed) == (0, _report(installed))

    skills[0].unlink()
    expected = _report(installed, status="FAIL")
    assert _doctor(monkeypatch, capsys, installed) == (1, expected)


def test_required_files_and_their_fallback_locations(
    monkeypatch: Any, capsys: Any, installed: Path
) -> None:
    payload_prompt = installed / ".agentic" / "MASTER_PROMPT.md"
    (installed / "MASTER_PROMPT.md").write_text(payload_prompt.read_text(encoding="utf-8"))
    payload_prompt.unlink()
    payload_schema = installed / ".agentic" / "schemas" / "agentic-config.schema.json"
    (installed / "schemas").mkdir()
    shutil.copy(payload_schema, installed / "schemas" / payload_schema.name)
    payload_schema.unlink()
    assert _doctor(monkeypatch, capsys, installed) == (0, _report(installed))

    (installed / "MASTER_PROMPT.md").unlink()
    (installed / "schemas" / payload_schema.name).unlink()
    expected = _report(installed, master_prompt=False, config_schema=False, status="FAIL")
    assert _doctor(monkeypatch, capsys, installed) == (1, expected)


def test_missing_agents_file_fails(monkeypatch: Any, capsys: Any, installed: Path) -> None:
    (installed / "AGENTS.md").unlink()
    expected = _report(installed, agents_md=False, status="FAIL")
    assert _doctor(monkeypatch, capsys, installed) == (1, expected)
