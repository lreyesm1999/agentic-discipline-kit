"""The edges of zero-touch operation: the inputs a real repository can hand it.

A project with no quality configuration, one whose gates prove nothing about behaviour, an
empty repository, a database written by a newer kit, a repair that fails halfway, a project
that is not a git repository. Each one must produce a precise answer, never a crash and
never a guess.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline import cli as installer
from agentic_discipline import readiness, repair
from agentic_discipline.bootstrap import initialize_project
from agentic_discipline.common import AgenticError, run_git
from agentic_discipline.control import cli, preflight, work
from agentic_discipline.control.plane import Plane, adopt

REQUEST = "Add a total to src/app.py"


def _project(root: Path, *, git: bool = True, adopted: bool = True) -> Path:
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='r'\nversion='0.1'\n", encoding="utf-8")
    (root / "src" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "tests" / "test_app.py").write_text(
        "def test_ok() -> None:\n    pass\n", encoding="utf-8"
    )
    if git:
        run_git(["init"], cwd=root)
    initialize_project(root, adopt=None if adopted else False)
    return root


def _gates(root: Path, gates: list[dict[str, Any]]) -> None:
    path = root / "agentic.config.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    config["gates"] = gates
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")


def _check(report: dict[str, Any], name: str) -> dict[str, Any]:
    return next(check for check in report["checks"] if check["name"] == name)


# --- deriving work from what the project records -----------------------------------------


def test_a_project_without_a_quality_configuration_is_asked_which_command_proves_the_work(
    tmp_path: Path,
) -> None:
    root = _project(tmp_path / "p")
    (root / "agentic.config.json").unlink()
    with Plane(root) as plane:
        derived = work.derive(plane, REQUEST)

    decisions = [decision["decision"] for decision in derived["decisions"]]
    assert "conflicting_requirements" in decisions
    question = next(d for d in derived["decisions"] if d["decision"] == "conflicting_requirements")
    assert question["question"] == "Which command proves this work?"
    assert question["why"] == "no quality configuration to take verifiers from"


def test_an_unreadable_quality_configuration_is_named_rather_than_guessed_around(
    tmp_path: Path,
) -> None:
    root = _project(tmp_path / "p")
    (root / "agentic.config.json").write_text("{not json", encoding="utf-8")
    with Plane(root) as plane:
        derived = work.derive(plane, REQUEST)

    why = next(
        d["why"] for d in derived["decisions"] if d["decision"] == "conflicting_requirements"
    )
    assert why.startswith("the quality configuration cannot be read:")


def test_gates_that_prove_nothing_about_behaviour_are_not_passed_off_as_proof(
    tmp_path: Path,
) -> None:
    """A linter is worth running and says nothing about whether the feature works."""

    root = _project(tmp_path / "p")
    _gates(
        root,
        [
            {"name": "lint", "command": ["ruff", "check", "."]},
            {"name": "types", "command": ["mypy", "src"]},
        ],
    )
    with Plane(root) as plane:
        plane.reconcile()
        derived = work.derive(plane, REQUEST)

    why = next(
        d["why"] for d in derived["decisions"] if d["decision"] == "conflicting_requirements"
    )
    assert (
        why == "none of the required gates in agentic.config.json proves behaviour: static_analysis"
    )
    assert derived["contract"]["verification"] == []


def test_a_task_waits_for_the_open_work_its_scope_depends_on(tmp_path: Path) -> None:
    root = _project(tmp_path / "p")
    _gates(root, [{"name": "tests", "command": [sys.executable, "-c", "pass"]}])
    (root / "src" / "other.py").write_text("OTHER = 2\n", encoding="utf-8")
    with Plane(root) as plane:
        plane.reconcile()
        first = work.start(plane, REQUEST, claim=False)
        # Wider than the first task, so it is not the same work: it depends on it instead.
        second = work.start(plane, "Share a constant between src/app.py and src/other.py")

        assert second["task"]["dependencies"] == [first["task"]["id"]]
        assert second["state"] == "WAITING"
        assert second["readiness"]["waiting_for"] == [first["task"]["id"]]
        assert "Not ready because:" in work.render(second)


def test_a_project_on_the_2_0_schema_gets_its_criteria_as_what_is_outstanding(
    tmp_path: Path,
) -> None:
    """Without the assurance engine there are no obligations to compile, and the acceptance
    criteria are what completion is measured against, as in 2.0."""

    root = _project(tmp_path / "p")
    _gates(root, [{"name": "tests", "command": [sys.executable, "-c", "pass"]}])
    with sqlite3.connect(root / readiness.STATE_DB) as db:
        db.execute("UPDATE meta SET value='1' WHERE key='schema_version'")
    with Plane(root) as plane:
        plane.reconcile()
        started = work.start(plane, REQUEST)
        assert plane.store.list("obligation") == []
        assert work._outstanding(plane, started["task"]) == [REQUEST]


# --- readiness and repair at the edges ---------------------------------------------------


def test_a_database_written_by_a_newer_kit_is_broken_rather_than_read(tmp_path: Path) -> None:
    root = _project(tmp_path / "p")
    with sqlite3.connect(root / readiness.STATE_DB) as db:
        db.execute("UPDATE meta SET value='9' WHERE key='schema_version'")

    report = readiness.inspect(root)

    assert report["execution_readiness"] == "BROKEN"
    assert _check(report, "control_plane")["status"] == "FAIL"


def test_an_audit_chain_emptied_of_its_history_is_broken(tmp_path: Path) -> None:
    root = _project(tmp_path / "p")
    with sqlite3.connect(root / readiness.STATE_DB) as db:
        db.execute("DROP TRIGGER events_no_delete")
        db.execute("DELETE FROM events")

    report = readiness.inspect(root)

    assert _check(report, "control_plane")["detail"] == "the audit chain holds no history"
    assert report["execution_readiness"] == "BROKEN"


def test_a_plane_without_a_project_record_is_reported_as_such(tmp_path: Path) -> None:
    root = _project(tmp_path / "p")
    with sqlite3.connect(root / readiness.STATE_DB) as db:
        db.execute("DELETE FROM records WHERE kind='project'")

    adoption = _check(readiness.inspect(root, deep=False), "project_adoption")

    assert (adoption["status"], adoption["detail"]) == (
        "MISSING",
        "the control plane holds no project record",
    )


def test_an_empty_repository_is_adopted_and_asks_to_be_indexed_once_it_has_files(
    tmp_path: Path,
) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    run_git(["init"], cwd=root)
    adopt(root)
    (root / "agentic.config.json").write_text("{}", encoding="utf-8")

    knowledge = _check(readiness.inspect(root, deep=False), "knowledge")

    assert (knowledge["status"], knowledge["repair"]) == ("MISSING", "agentic reconcile")
    assert knowledge["detail"] == "the project has never been indexed"


def test_adapters_that_cannot_be_rendered_are_a_failure_not_a_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agentic_discipline import adapters

    root = _project(tmp_path / "p")

    def unavailable(*args: Any, **kwargs: Any) -> Any:
        raise AgenticError("packaged Agentic Discipline contracts were not found")

    monkeypatch.setattr(adapters, "sync_adapters", unavailable)
    check = _check(readiness.inspect(root, deep=False), "agent_adapter")

    assert (check["status"], check["detail"]) == (
        "FAIL",
        "packaged Agentic Discipline contracts were not found",
    )


def test_repair_never_turns_a_directory_into_a_git_repository(tmp_path: Path) -> None:
    root = _project(tmp_path / "p", git=False)

    result = repair.apply(root)

    assert all(entry["action"] != "git init" for entry in result["repaired"])
    assert not (root / ".git").exists()
    assert _check(result["readiness"], "git_integration")["status"] == "MISSING"


def test_a_repair_that_fails_is_reported_and_the_rest_still_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path / "p", adopted=False)
    (root / "AGENTS.md").write_text("# replaced\n", encoding="utf-8")

    def refuse(path: Path) -> str:
        raise AgenticError("the disk said no")

    failing = repair.Repair("initialise the control plane", (".agentic/control",), refuse)
    monkeypatch.setitem(repair.REPAIRS, "control_plane", failing)

    result = repair.apply(root)

    assert [entry["outcome"] for entry in result["failed"]] == ["failed: the disk said no"]
    assert [entry["action"] for entry in result["repaired"]] == ["recompile the agent surfaces"]
    assert result["status"] == "FAIL"
    text = preflight.render({**preflight.run(root, repair_first=False), "failed": result["failed"]})
    assert "Could not repair:" in text
    assert "the disk said no" in text


def test_an_audit_write_that_cannot_land_does_not_undo_the_repair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path / "p")
    (root / "AGENTS.md").write_text("# replaced\n", encoding="utf-8")
    original = Plane.__enter__

    def locked(self: Plane) -> Plane:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(Plane, "__enter__", locked)
    result = repair.apply(root, deep=False)
    monkeypatch.setattr(Plane, "__enter__", original)

    assert [entry["action"] for entry in result["repaired"]] == ["recompile the agent surfaces"]
    assert "Agentic Discipline" in (root / "AGENTS.md").read_text(encoding="utf-8")


# --- the command lines ----------------------------------------------------------------------


def _main(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], *argv: str
) -> tuple[int, str]:
    monkeypatch.setattr(sys, "argv", ["agentic", *argv])
    capsys.readouterr()
    try:
        cli.main()
        code = 0
    except SystemExit as exit_:
        code = int(exit_.code or 0)
    return code, capsys.readouterr().out


def test_the_preflight_command_prints_its_mode_and_what_it_repaired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path / "p", adopted=False)

    code, out = _main(monkeypatch, capsys, "--root", str(root), "preflight")

    assert code == 0
    assert out.startswith("Execution mode: FULL")
    assert "Repaired automatically:" in out
    assert "initialise the control plane" in out


def test_a_blocked_request_prints_the_preflight_that_blocked_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path / "p", adopted=False)
    (root / readiness.CONTROL_DIR).mkdir(parents=True)

    code, out = _main(monkeypatch, capsys, "--root", str(root), "work", "start", REQUEST)

    assert code == 2
    assert out.startswith("Execution mode: BLOCKED")
    assert "Do not proceed" in out


def test_the_work_commands_cover_the_whole_cycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path / "p")
    _gates(root, [{"name": "tests", "command": [sys.executable, "-c", "pass"]}])
    with Plane(root) as plane:
        plane.reconcile()
    session_file = tmp_path / "session.json"

    code, out = _main(monkeypatch, capsys, "--root", str(root), "work", "derive", REQUEST, "--json")
    assert code == 0
    assert json.loads(out)["data"]["contract"]["scope"] == ["src/app.py"]

    code, out = _main(
        monkeypatch,
        capsys,
        "--root",
        str(root),
        "work",
        "start",
        REQUEST,
        "--session-out",
        str(session_file),
    )
    assert code == 0 and out.startswith("Work state: READY")
    task = json.loads(
        _main(monkeypatch, capsys, "--root", str(root), "work", "start", REQUEST, "--json")[1]
    )["data"]["task"]["id"]

    code, out = _main(
        monkeypatch,
        capsys,
        "--root",
        str(root),
        "work",
        "verify",
        "--task",
        task,
        "--session-file",
        str(session_file),
        "--json",
    )
    assert json.loads(out)["data"]["status"] == "PASS"
    code, out = _main(
        monkeypatch,
        capsys,
        "--root",
        str(root),
        "work",
        "finish",
        "--task",
        task,
        "--session-file",
        str(session_file),
        "--json",
    )
    assert json.loads(out)["data"]["state"] == "COMPLETED"
    code, out = _main(monkeypatch, capsys, "--root", str(root), "work", "next", "--json")
    assert json.loads(out)["data"] is None


def test_the_repair_command_reports_a_dry_run_and_its_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path / "p", adopted=False)
    monkeypatch.chdir(root)

    installer.command_repair(argparse.Namespace(dry_run=True, fast=True, json=False))
    out = capsys.readouterr().out
    assert out.startswith("DRY RUN - nothing was written.")
    assert "initialise the control plane: would run" in out

    def refuse(path: Path) -> str:
        raise AgenticError("the disk said no")

    monkeypatch.setitem(
        repair.REPAIRS, "control_plane", repair.Repair("initialise the control plane", (), refuse)
    )
    assert installer.command_repair(argparse.Namespace(dry_run=False, fast=True, json=False)) == 1
    assert "! initialise the control plane: failed: the disk said no" in capsys.readouterr().out

    assert installer.command_repair(argparse.Namespace(dry_run=True, fast=True, json=True)) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is True


# --- the branches that are behaviour rather than defence ------------------------------------


def test_the_database_s_own_refusal_names_a_schema_from_a_newer_kit(tmp_path: Path) -> None:
    root = _project(tmp_path / "p")
    with sqlite3.connect(root / readiness.STATE_DB) as db:
        db.execute("UPDATE meta SET value='9' WHERE key='schema_version'")

    detail = _check(readiness.inspect(root), "control_plane")["detail"]

    assert detail.startswith("the state database cannot be opened:")
    assert "Unsupported database version" in detail


def test_the_kit_s_own_checkout_without_a_plane_is_a_choice(tmp_path: Path) -> None:
    checkout = tmp_path / "kit"
    (checkout / "disciplines" / "01-source").mkdir(parents=True)
    (checkout / "config" / "profiles").mkdir(parents=True)
    (checkout / "disciplines" / "01-source" / "SKILL.md").write_text("x\n", encoding="utf-8")
    (checkout / "AGENTS.md").write_text("# kit\n", encoding="utf-8")

    report = readiness.inspect(checkout, deep=False)

    control = _check(report, "control_plane")
    assert (control["status"], control["repair"]) == ("OFF", "agentic adopt")
    assert report["execution_readiness"] == "DEGRADED"


def test_a_plane_without_an_execution_policy_cannot_orchestrate(tmp_path: Path) -> None:
    root = _project(tmp_path / "p")
    with sqlite3.connect(root / readiness.STATE_DB) as db:
        db.execute("DELETE FROM records WHERE kind='policy'")

    orchestration = _check(readiness.inspect(root, deep=False), "task_orchestration")

    assert (orchestration["status"], orchestration["detail"]) == (
        "MISSING",
        "no execution policy is recorded",
    )


def test_a_checkpoint_with_nothing_new_restates_what_was_already_proven(tmp_path: Path) -> None:
    root = _project(tmp_path / "p")
    _gates(root, [{"name": "tests", "command": [sys.executable, "-c", "pass"]}])
    with Plane(root) as plane:
        plane.reconcile()
        started = work.start(plane, REQUEST)
        task, session = started["task"], str(started["session"])
        work.verify(plane, task["id"], session)
        work.checkpoint(plane, task["id"], session, reason="slice_complete")

        again = work.checkpoint(plane, task["id"], session, reason="handoff")

    assert again["context"]["completed_work"] == ["previously verified: unit"]
    assert again["context"]["commands_run"] == []


def test_one_repair_answers_two_checks_and_runs_once(tmp_path: Path) -> None:
    """A payload missing a discipline and a file of its own is one reinstall, not two."""

    root = _project(tmp_path / "p")
    (root / ".agentic" / "MASTER_PROMPT.md").unlink()
    skill = root / ".agentic" / "skills" / "05-coding"
    for child in sorted(skill.rglob("*"), reverse=True):
        child.unlink() if child.is_file() else child.rmdir()
    skill.rmdir()

    chosen = repair.plan(readiness.inspect(root, deep=False))

    assert [name for name, _ in chosen].count("installation") == 1
    assert "disciplines" not in [name for name, _ in chosen]
    assert repair.apply(root)["status"] == "PASS"


def test_a_stale_requirement_does_not_supply_acceptance(tmp_path: Path) -> None:
    root = _project(tmp_path / "p")
    _gates(root, [{"name": "tests", "command": [sys.executable, "-c", "pass"]}])
    with Plane(root) as plane:
        plane.reconcile()
        entity = plane.knowledge.apply(
            [
                {
                    "graph": "requirement",
                    "type": "requirement",
                    "name": "Totals are added in src/app.py",
                    "source_ref": "specs/requirements.md",
                    "authority": "human",
                    "confidence": 1,
                    "observation": "DECLARED",
                    "acceptance": ["an outdated criterion"],
                }
            ],
            plane.store.knowledge_version,
            "approved requirement",
        )["entities"][0]
        with plane.store.transaction():
            plane.store.put("entity", {**entity, "stale": True}, expected=entity["version"])

        derived = work.derive(plane, REQUEST)

    assert derived["contract"]["acceptance"] == [REQUEST]
    assert derived["contract"]["requirements"] == []
