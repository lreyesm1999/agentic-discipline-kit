"""What `init`, `doctor` and `repair` print and decide, from the readiness they are handed.

The commands are thin: they ask readiness what state the project is in and say so. These
cases hand them the state directly, so the verdict each state produces, the options that
reach readiness, and every line a person reads are pinned exactly.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline import cli, readiness
from agentic_discipline.bootstrap import initialize_project
from agentic_discipline.common import run_git
from agentic_discipline.control.plane import adopt


def _check(
    name: str,
    status: str = "PASS",
    *,
    advisory: bool = False,
    caused_by: str | None = None,
    repair: str | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "label": name.replace("_", " ").capitalize(),
        "status": status,
        "detail": f"{name} detail",
        "advisory": advisory,
        "caused_by": caused_by,
        "repair": repair,
    }


def _printed(capsys: pytest.CaptureFixture[str]) -> list[str]:
    return capsys.readouterr().out.splitlines()


# --- repair --------------------------------------------------------------------------------


def _repair(**fields: Any) -> dict[str, Any]:
    return {
        "dry_run": False,
        "before": "PARTIAL",
        "planned": [],
        "repaired": [],
        "failed": [],
        "readiness": {"execution_readiness": "READY", "checks": []},
        **fields,
    }


def test_a_dry_run_lists_its_plan_and_only_what_no_repair_answers(
    capsys: pytest.CaptureFixture[str],
) -> None:
    checks = [
        _check("installation"),
        _check("version", "STALE", advisory=True),
        _check("control_plane", "MISSING"),
        _check("knowledge", "MISSING", caused_by="control_plane"),
        _check("git_integration", "MISSING"),
        _check("task_orchestration", "MISSING", caused_by="git_integration"),
        _check("agent_adapter", "FAIL"),
    ]
    result = _repair(
        dry_run=True,
        planned=[{"action": "adopt", "outcome": "would run", "check": "control_plane"}],
        readiness={"execution_readiness": "PARTIAL", "checks": checks},
    )

    cli._render_repair(result)

    assert _printed(capsys) == [
        "DRY RUN - nothing was written.",
        "Execution readiness  PARTIAL -> PARTIAL",
        "",
        "  - adopt: would run",
        "",
        "Left for a person to decide:",
        "  - Git integration (MISSING): git_integration detail",
        "  - Agent adapter (FAIL): agent_adapter detail",
    ]


def test_a_run_lists_what_it_did_and_what_failed(capsys: pytest.CaptureFixture[str]) -> None:
    cli._render_repair(
        _repair(
            repaired=[{"action": "reindex", "outcome": "done", "check": "knowledge"}],
            failed=[{"action": "adopt", "outcome": "failed: no", "check": "control_plane"}],
        )
    )

    assert _printed(capsys) == [
        "Execution readiness  PARTIAL -> READY",
        "",
        "  - reindex: done",
        "  ! adopt: failed: no",
    ]


@pytest.mark.parametrize("field", ["planned", "repaired", "failed"])
def test_any_one_entry_means_there_was_something_to_repair(
    field: str, capsys: pytest.CaptureFixture[str]
) -> None:
    cli._render_repair(_repair(**{field: [{"action": "a", "outcome": "o", "check": "c"}]}))

    assert "  Nothing to repair." not in _printed(capsys)


def test_nothing_to_repair_says_so(capsys: pytest.CaptureFixture[str]) -> None:
    cli._render_repair(_repair())

    assert _printed(capsys) == [
        "Execution readiness  PARTIAL -> READY",
        "",
        "  Nothing to repair.",
    ]


def test_the_repair_command_passes_its_options_through(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    seen: list[dict[str, Any]] = []

    def apply(root: Path, *, dry_run: bool, deep: bool) -> dict[str, Any]:
        seen.append({"dry_run": dry_run, "deep": deep})
        return _repair(status="PASS")

    monkeypatch.setattr(cli, "_doctor_root", lambda: tmp_path)
    monkeypatch.setattr(cli.repair, "apply", apply)

    assert cli.command_repair(argparse.Namespace(dry_run=True, fast=False, json=True)) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "PASS"
    assert cli.command_repair(argparse.Namespace(dry_run=False, fast=True, json=False)) == 0
    assert _printed(capsys)[0] == "Execution readiness  PARTIAL -> READY"
    assert seen == [{"dry_run": True, "deep": True}, {"dry_run": False, "deep": False}]


# --- doctor --------------------------------------------------------------------------------


@pytest.fixture
def installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    initialize_project(root)
    run_git(["init"], cwd=root)
    adopt(root)
    monkeypatch.chdir(root)
    return root


def _staged(monkeypatch: pytest.MonkeyPatch, state: str) -> list[bool]:
    scans: list[bool] = []

    def inspect(root: Path, *, deep: bool, config: Path | None) -> dict[str, Any]:
        scans.append(deep)
        return {"execution_readiness": state, "checks": []}

    monkeypatch.setattr(readiness, "inspect", inspect)
    return scans


def _doctor(capsys: pytest.CaptureFixture[str], **args: Any) -> tuple[int, str]:
    namespace = argparse.Namespace(
        **{"config": None, "check_tools": False, "json": True, "fast": False, **args}
    )
    code = cli.command_doctor(namespace)
    output = capsys.readouterr().out
    return code, json.loads(output)["status"] if namespace.json else output


@pytest.mark.parametrize(
    ("state", "code", "status"),
    [("READY", 0, "PASS"), ("DEGRADED", 0, "PASS"), ("PARTIAL", 1, "FAIL")],
)
def test_the_doctor_s_verdict_follows_execution_readiness(
    installed: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    state: str,
    code: int,
    status: str,
) -> None:
    _staged(monkeypatch, state)

    assert _doctor(capsys) == (code, status)


def test_the_doctor_scans_the_tree_unless_asked_to_be_fast(
    installed: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    deep = _staged(monkeypatch, "READY")

    _doctor(capsys)
    _doctor(capsys, fast=True)

    assert deep == [True, False]


def test_the_doctor_prints_the_table_unless_asked_for_json(
    installed: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _staged(monkeypatch, "READY")
    monkeypatch.setattr(readiness, "render", lambda report: "the table")

    assert _doctor(capsys, json=False) == (0, "the table\n")


def test_each_installation_fact_fails_the_doctor_on_its_own(
    installed: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _staged(monkeypatch, "READY")
    assert _doctor(capsys) == (0, "PASS")

    monkeypatch.setattr(cli, "_installed_skills", lambda root: 0)
    assert _doctor(capsys) == (1, "FAIL")
    monkeypatch.undo()

    _staged(monkeypatch, "READY")
    (installed / "AGENTS.md").rename(installed / "AGENTS.bak")
    monkeypatch.setattr(cli, "_doctor_root", lambda: installed)
    assert _doctor(capsys) == (1, "FAIL")


# --- init ----------------------------------------------------------------------------------


def _init(**fields: Any) -> dict[str, Any]:
    return {
        "target": ".",
        "detections": [{"label": "Python", "root": "."}],
        "disciplines": ["a", "b"],
        "adapters": ["claude"],
        "adapter_labels": ["Claude Code"],
        "relaxed_gates": [],
        "gates": 3,
        "actions": ["WRITE a", "WRITE b", "SKIP c"],
        **fields,
    }


def test_an_install_that_did_not_try_the_control_plane_says_so(
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli._render_init(_init())

    lines = _printed(capsys)
    assert "  Control plane    not attempted" in lines
    assert lines[-1] == "Next:  agentic-discipline init        (this run wrote nothing)"


def test_a_rules_only_install_says_orchestration_is_unavailable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = {"execution_readiness": "DEGRADED", "reason": "rules only", "checks": []}

    cli._render_init(_init(readiness=report))

    assert _printed(capsys)[-3:] == [
        "Status: RULES ONLY - orchestration is not available",
        "",
        "Next:  agentic-discipline doctor --check-tools",
    ]


def test_an_unusable_install_lists_every_check_that_needs_attention(
    capsys: pytest.CaptureFixture[str],
) -> None:
    checks = [
        _check("installation"),
        _check("version", "STALE", advisory=True),
        _check("control_plane", "MISSING", repair="agentic-discipline repair"),
        _check("knowledge", "FAIL"),
    ]
    report = {"execution_readiness": "PARTIAL", "reason": "no plane", "checks": checks}

    cli._render_init(_init(readiness=report))

    lines = _printed(capsys)
    assert lines[lines.index("Status: PARTIAL") :] == [
        "Status: PARTIAL",
        "",
        "Reason: no plane",
        "  - Control plane (MISSING): control_plane detail",
        "    Repair: agentic-discipline repair",
        "  - Knowledge (FAIL): knowledge detail",
        "",
        "Next:  agentic-discipline doctor --check-tools",
    ]


@pytest.mark.parametrize(("state", "code"), [("READY", 0), ("DEGRADED", 0), ("PARTIAL", 1)])
def test_the_init_command_exits_on_whether_the_install_is_usable(
    monkeypatch: pytest.MonkeyPatch, state: str, code: int
) -> None:
    report = {"execution_readiness": state, "reason": "r", "checks": []}
    monkeypatch.setattr(cli, "initialize_project", lambda *a, **k: _init(readiness=report))
    monkeypatch.setattr(cli, "_json", lambda data: None)
    args = argparse.Namespace(
        target=".",
        profile=[],
        profile_file=[],
        force=False,
        max_depth=4,
        adapter=[],
        dry_run=False,
        rules_only=False,
        no_adopt=False,
        adopt=False,
        json=True,
    )

    assert cli.command_init(args) == code


@pytest.mark.parametrize(
    ("no_adopt", "adopt_flag", "choice"),
    [(False, False, None), (False, True, True), (True, False, False), (True, True, False)],
)
def test_the_adoption_choice_is_the_flags_given(
    no_adopt: bool, adopt_flag: bool, choice: bool | None
) -> None:
    args = argparse.Namespace(no_adopt=no_adopt, adopt=adopt_flag)

    assert cli._adopt_choice(args) is choice
