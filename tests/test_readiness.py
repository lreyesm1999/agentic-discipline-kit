"""Execution readiness, state by state.

The report these tests pin is the one that replaced a `doctor` which said PASS while the
control plane did not exist. So each case builds a project that is broken in exactly one
way and asserts the check that names it, the verdict it produces, and the repair offered.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline import cli, readiness
from agentic_discipline.bootstrap import initialize_project
from agentic_discipline.common import run_git
from agentic_discipline.control.plane import adopt


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    initialize_project(root)
    run_git(["init"], cwd=root)
    return root


def _check(report: dict[str, Any], name: str) -> dict[str, Any]:
    return next(check for check in report["checks"] if check["name"] == name)


def _adopted(root: Path) -> dict[str, Any]:
    adopt(root)
    return readiness.inspect(root)


def test_an_installed_project_without_a_control_plane_is_partial_and_says_so(
    project: Path,
) -> None:
    report = readiness.inspect(project)
    control = _check(report, "control_plane")
    assert (report["installation"], report["project"]) == ("PASS", "PARTIAL")
    assert report["execution_readiness"] == "PARTIAL"
    assert report["reason"] == "Control plane: the control plane has never been initialised here"
    assert (control["status"], control["repair"], control["repairable"]) == (
        "MISSING",
        "agentic adopt",
        True,
    )
    # Everything the control plane holds is reported as missing for that one reason, rather
    # than as four unrelated faults.
    for name in ("project_adoption", "knowledge", "task_orchestration"):
        assert _check(report, name)["status"] == "MISSING"
        assert "control plane" in _check(report, name)["detail"]


def test_an_adopted_project_is_ready(project: Path) -> None:
    report = _adopted(project)
    assert (report["installation"], report["project"]) == ("PASS", "PASS")
    assert (report["execution_readiness"], report["status"]) == ("READY", "PASS")
    assert report["reason"] == "every check passes; the full workflow is available"
    assert report["repairs"] == []


def test_rules_only_is_a_recorded_choice_and_reads_as_degraded(project: Path) -> None:
    payload = project / ".agentic" / "config.json"
    data = json.loads(payload.read_text(encoding="utf-8"))
    payload.write_text(
        json.dumps({**data, "control": {"mode": "rules-only"}}, indent=2), encoding="utf-8"
    )
    report = readiness.inspect(project)
    control = _check(report, "control_plane")
    assert (report["control_mode"], control["status"]) == ("rules-only", "OFF")
    # A choice is not a fault: nothing is offered as an automatic repair, and the state is
    # not PARTIAL, but the report still says orchestration is unavailable.
    assert (report["execution_readiness"], control["repairable"]) == ("DEGRADED", False)
    assert "on purpose" in report["reason"]


def test_a_control_directory_without_a_database_is_broken_and_never_repaired_silently(
    project: Path,
) -> None:
    (project / readiness.CONTROL_DIR).mkdir(parents=True)
    report = readiness.inspect(project)
    control = _check(report, "control_plane")
    assert (report["execution_readiness"], control["status"]) == ("BROKEN", "FAIL")
    assert control["repair"] is None
    assert "second one would split the project's history" in control["detail"]


def test_an_unreadable_state_database_is_broken(project: Path) -> None:
    adopt(project)
    (project / readiness.STATE_DB).write_bytes(b"not a database")
    report = readiness.inspect(project)
    assert report["execution_readiness"] == "BROKEN"
    assert _check(report, "control_plane")["status"] == "FAIL"


def test_an_altered_history_is_broken(project: Path) -> None:
    adopt(project)
    with sqlite3.connect(project / readiness.STATE_DB) as db:
        db.execute("DROP TRIGGER events_no_update")
        db.execute("UPDATE events SET actor='someone-else' WHERE seq=(SELECT MIN(seq) FROM events)")
    report = readiness.inspect(project)
    assert report["execution_readiness"] == "BROKEN"
    assert "history has been altered" in _check(report, "control_plane")["detail"]


def test_a_plane_adopted_for_another_checkout_is_broken(project: Path, tmp_path: Path) -> None:
    adopt(project)
    moved = tmp_path / "moved"
    project.rename(moved)
    report = readiness.inspect(moved)
    adoption = _check(report, "project_adoption")
    assert (report["execution_readiness"], adoption["status"]) == ("BROKEN", "FAIL")
    assert "not for this checkout" in adoption["detail"]


def test_knowledge_drifts_with_the_tree_without_blocking_execution(project: Path) -> None:
    """An index a few edits behind is the normal state of an active repository. It is
    reported, and starting work repairs it, but it is not a gap in readiness."""

    assert _adopted(project)["execution_readiness"] == "READY"
    (project / "extra.py").write_text("value = 2\n", encoding="utf-8")
    report = readiness.inspect(project)
    knowledge = _check(report, "knowledge")
    assert (knowledge["status"], knowledge["advisory"]) == ("STALE", True)
    assert (knowledge["repair"], knowledge["repairable"]) == ("agentic reconcile", True)
    assert (report["execution_readiness"], report["drift"]) == ("READY", ["knowledge"])
    assert report["project"] == "PASS"
    assert "the tree has changed since it was last indexed" in report["reason"]

    from agentic_discipline.control.plane import Plane

    with Plane(project) as plane:
        plane.reconcile()
    after = readiness.inspect(project)
    assert (after["execution_readiness"], after["drift"]) == ("READY", [])


def test_only_the_deep_scan_sees_the_drift(project: Path) -> None:
    adopt(project)
    (project / "extra.py").write_text("value = 2\n", encoding="utf-8")
    assert readiness.inspect(project, deep=False)["drift"] == []
    assert readiness.inspect(project, deep=True)["drift"] == ["knowledge"]


def test_stale_adapters_and_pruned_disciplines_are_repairable(project: Path) -> None:
    adopt(project)
    (project / "AGENTS.md").write_text("# mine only\n", encoding="utf-8")
    pruned = project / ".agentic" / "skills" / "05-coding"
    for path in sorted(pruned.rglob("*"), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()
    pruned.rmdir()
    report = readiness.inspect(project)
    assert report["execution_readiness"] == "PARTIAL"
    assert _check(report, "agent_adapter")["status"] == "STALE"
    assert _check(report, "disciplines")["status"] == "STALE"
    assert "agentic-discipline adapters sync" in report["repairs"]


def test_an_empty_directory_is_not_initialized(tmp_path: Path) -> None:
    report = readiness.inspect(tmp_path)
    assert (report["execution_readiness"], report["shape"]) == ("NOT_INITIALIZED", "absent")
    assert _check(report, "installation")["repair"] == "agentic-discipline init"


def test_the_kit_checkout_is_not_a_project_that_installed_itself(tmp_path: Path) -> None:
    """Adopting the kit creates `.agentic/`, which must not read as an installed payload."""

    checkout = tmp_path / "kit"
    (checkout / "disciplines" / "01-source").mkdir(parents=True)
    (checkout / "config" / "profiles").mkdir(parents=True)
    (checkout / "disciplines" / "01-source" / "SKILL.md").write_text("x\n", encoding="utf-8")
    (checkout / "AGENTS.md").write_text("# kit\n", encoding="utf-8")
    assert readiness.shape(checkout) == "checkout"
    (checkout / ".agentic" / "control").mkdir(parents=True)
    assert readiness.shape(checkout) == "checkout"
    report = readiness.inspect(checkout, deep=False)
    # The source tree carries the disciplines themselves, so nothing is emitted into it.
    assert _check(report, "agent_adapter")["status"] == "PASS"
    assert _check(report, "installation")["status"] == "PASS"


def test_a_project_without_git_cannot_bind_a_change_to_a_commit(tmp_path: Path) -> None:
    root = tmp_path / "nogit"
    root.mkdir()
    initialize_project(root)
    report = readiness.inspect(root, deep=False)
    git = _check(report, "git_integration")
    assert (git["status"], git["repair"]) == ("MISSING", "git init")
    assert report["execution_readiness"] == "PARTIAL"


def _doctor(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], root: Path, **args: Any
) -> tuple[int, str]:
    monkeypatch.chdir(root)
    capsys.readouterr()
    code = cli.command_doctor(argparse.Namespace(config=None, check_tools=False, **args))
    return code, capsys.readouterr().out


def test_doctor_prints_the_table_and_exits_on_the_verdict(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], project: Path
) -> None:
    code, out = _doctor(monkeypatch, capsys, project, json=False, fast=False)
    assert code == 1
    assert "Execution readiness  PARTIAL" in out
    assert "Repair: agentic adopt" in out

    adopt(project)
    code, out = _doctor(monkeypatch, capsys, project, json=False, fast=False)
    assert (code, "Execution readiness  READY" in out) == (0, True)
    assert "Outstanding" not in out


def test_doctor_keeps_its_machine_report_for_the_callers_that_parse_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], project: Path
) -> None:
    adopt(project)
    code, out = _doctor(monkeypatch, capsys, project, json=True, fast=False)
    report = json.loads(out)
    assert code == 0
    # The installation facts 2.0 published are still there, alongside the new verdict.
    assert {"python", "git", "package_version", "agents_md", "skills", "status"} <= report.keys()
    assert report["status"] == "PASS"
    assert report["readiness"]["execution_readiness"] == "READY"
