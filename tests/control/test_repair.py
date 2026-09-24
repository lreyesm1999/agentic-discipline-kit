"""Safe auto-repair: what it fixes, what it refuses, and what it records.

The value of a repair is that nobody has to know it happened. The risk is that it destroys
something while nobody is looking, so every case here checks both halves: the gap closes,
and existing work, hand-edited files and unexplained state come out untouched.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from conftest import checkpoint, contract

from agentic_discipline import readiness, repair
from agentic_discipline.bootstrap import initialize_project
from agentic_discipline.common import run_git
from agentic_discipline.control.plane import Plane


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (root / "app.py").write_text("value = 1\n", encoding="utf-8")
    (root / "test_app.py").write_text("import app\n", encoding="utf-8")
    run_git(["init"], cwd=root)
    initialize_project(root)
    return root


def _remove(path: Path) -> None:
    for child in sorted(path.rglob("*"), reverse=True):
        child.unlink() if child.is_file() else child.rmdir()
    path.rmdir()


def _actions(result: dict[str, Any]) -> list[str]:
    return [str(entry["action"]) for entry in result["repaired"]]


def test_a_missing_control_plane_is_restored_in_one_action(project: Path) -> None:
    _remove(project / readiness.CONTROL_DIR)
    assert readiness.inspect(project)["execution_readiness"] == "PARTIAL"

    result = repair.apply(project)

    assert result["status"] == "PASS"
    assert (result["before"], result["readiness"]["execution_readiness"]) == ("PARTIAL", "READY")
    # Adoption restores the project record, the index and the orchestration together, so the
    # three checks that depend on it do not each ask for a repair of their own.
    assert _actions(result) == ["initialise the control plane"]
    assert result["repaired"][0]["outcome"] == "adopted the repository and indexed the project"


def test_stale_adapters_and_a_pruned_payload_are_rebuilt(project: Path) -> None:
    (project / "AGENTS.md").write_text("# replaced by hand\n", encoding="utf-8")
    _remove(project / ".agentic" / "skills" / "05-coding")

    result = repair.apply(project)

    assert result["status"] == "PASS"
    # In dependency order, and the reindex last: reinstalling the payload writes files, so the
    # index has to catch up after the writing is done rather than before it.
    assert _actions(result) == [
        "reinstall the payload",
        "recompile the agent surfaces",
        "reindex the project",
    ]
    outcomes = [item["outcome"] for item in result["repaired"]]
    assert any(item.startswith("reinstalled the missing payload files (") for item in outcomes)
    assert any(item.startswith("recompiled the agent surfaces (") for item in outcomes)
    assert result["readiness"]["drift"] == []
    assert readiness.skill_count(project) == readiness.EXPECTED_DISCIPLINES
    assert "Agentic Discipline" in (project / "AGENTS.md").read_text(encoding="utf-8")


def test_a_hand_edited_configuration_survives_a_repair(project: Path) -> None:
    """The payload is filled in, never overwritten: a project's own edits are its own."""

    config = project / "agentic.config.json"
    edited = {**json.loads(config.read_text(encoding="utf-8")), "project": "renamed-by-hand"}
    config.write_text(json.dumps(edited, indent=2), encoding="utf-8")
    risk = project / ".agentic" / "config" / "risk-weights.json"
    risk.write_text('{"mine": true}', encoding="utf-8")
    _remove(project / ".agentic" / "skills" / "05-coding")

    repair.apply(project)

    assert json.loads(config.read_text(encoding="utf-8"))["project"] == "renamed-by-hand"
    assert json.loads(risk.read_text(encoding="utf-8")) == {"mine": True}


def test_drift_is_reindexed_without_disturbing_anything_else(project: Path) -> None:
    (project / "feature.py").write_text("def added() -> int:\n    return 2\n", encoding="utf-8")
    assert readiness.inspect(project)["drift"] == ["knowledge"]

    result = repair.apply(project)

    assert _actions(result) == ["reindex the project"]
    assert result["readiness"]["drift"] == []
    with Plane(project) as plane:
        assert "feature.py" in {e["path"] for e in plane.store.list("entity") if e.get("path")}


def test_work_in_progress_is_preserved(project: Path) -> None:
    with Plane(project) as plane:
        data = contract()
        plane.approve_command(data["verification"][0]["command"])
        task = plane.create_task(data)
        plane.ready(task["id"])
        session = plane.join("worker", ["code"])["session"]
        plane.claim(task["id"], session)
        plane.checkpoint(task["id"], session, checkpoint())
        before = plane.store.get(task["id"], "task")
        checkpoints = len(plane.store.list("checkpoint"))

    _remove(project / ".agentic" / "skills" / "05-coding")
    (project / "feature.py").write_text("value = 3\n", encoding="utf-8")
    assert repair.apply(project)["status"] == "PASS"

    with Plane(project) as plane:
        assert plane.store.get(task["id"], "task") == before
        assert len(plane.store.list("checkpoint")) == checkpoints
        assert len(plane.store.list("lease")) == 1


def test_an_unexplained_control_directory_is_never_repaired(project: Path) -> None:
    _remove(project / readiness.CONTROL_DIR)
    (project / readiness.CONTROL_DIR).mkdir(parents=True)

    result = repair.apply(project)

    assert result["status"] == "FAIL"
    assert (result["repaired"], result["failed"]) == ([], [])
    assert result["readiness"]["execution_readiness"] == "BROKEN"
    # Nothing was created beside it: a second database would split the project's history.
    assert list((project / readiness.CONTROL_DIR).iterdir()) == []


def test_an_altered_audit_chain_is_never_repaired(project: Path) -> None:
    import sqlite3

    with sqlite3.connect(project / readiness.STATE_DB) as db:
        db.execute("DROP TRIGGER events_no_update")
        db.execute("UPDATE events SET actor='someone' WHERE seq=(SELECT MIN(seq) FROM events)")

    result = repair.apply(project)

    assert (result["status"], result["repaired"]) == ("FAIL", [])
    assert result["readiness"]["execution_readiness"] == "BROKEN"


def test_a_repair_whose_cause_cannot_be_fixed_is_not_attempted(project: Path) -> None:
    """Reindexing needs a plane. Trying it anyway would report a failure that explains nothing."""

    _remove(project / readiness.CONTROL_DIR)
    (project / readiness.CONTROL_DIR).mkdir(parents=True)
    report = readiness.inspect(project)
    assert next(c for c in report["checks"] if c["name"] == "knowledge")["caused_by"] == (
        "control_plane"
    )
    assert repair.plan(report) == []


def test_nothing_to_repair_is_a_pass_that_writes_nothing(project: Path) -> None:
    result = repair.apply(project)
    assert (result["status"], result["repaired"], result["failed"]) == ("PASS", [], [])
    with Plane(project) as plane:
        events = plane.store.audit()["records"]
    assert repair.apply(project)["repaired"] == []
    with Plane(project) as plane:
        # No repair, no audit record: the chain only grows when something actually happened.
        assert plane.store.audit()["records"] == events


def test_every_repair_is_written_to_the_audit_chain(project: Path) -> None:
    _remove(project / ".agentic" / "skills" / "05-coding")

    repair.apply(project)

    with Plane(project) as plane:
        recorded = [
            event for event in plane.store.timeline() if event["action"] == "readiness.repair"
        ]
    assert len(recorded) == 1
    payload = recorded[0]["payload"]
    assert payload["repaired"] == [
        "reinstall the payload",
        "recompile the agent surfaces",
        "reindex the project",
    ]
    assert (payload["from"], payload["to"]) == ("PARTIAL", "READY")
    assert payload["failed"] == []


def test_a_dry_run_reports_the_plan_and_writes_nothing(project: Path) -> None:
    _remove(project / readiness.CONTROL_DIR)

    result = repair.apply(project, dry_run=True)

    assert result["dry_run"] is True
    assert [entry["action"] for entry in result["planned"]] == ["initialise the control plane"]
    assert result["repaired"] == []
    assert not (project / readiness.CONTROL_DIR).exists()


def test_reinstall_writes_only_missing_files_and_does_not_adopt(project: Path) -> None:
    before = (project / readiness.STATE_DB).exists()
    outcome = repair._reinstall(project)
    assert outcome.startswith("reinstalled the missing payload files (")
    assert outcome.endswith(" written)")
    written = int(outcome.split("(")[1].split(" ")[0])
    assert written == 1
    assert (project / readiness.STATE_DB).exists() is before


def test_resync_of_current_surfaces_rewrites_nothing(project: Path) -> None:
    assert repair._resync(project) == "recompiled the agent surfaces (0 file(s) rewritten)"


def test_a_repair_that_fails_does_not_cancel_the_next_one(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(root: Path) -> str:
        raise OSError("nope")

    payload = repair.PAYLOAD
    monkeypatch.setitem(
        repair.REPAIRS,
        "installation",
        repair.Repair(payload.action, payload.writes, boom),
    )
    (project / "AGENTS.md").unlink()
    result = repair.apply(project)
    checks = {item["check"] for item in result["failed"] + result["repaired"]}
    assert "installation" in checks
    assert "agent_adapter" in checks


def test_a_rules_only_project_is_left_alone(project: Path) -> None:
    _remove(project / readiness.CONTROL_DIR)
    payload = project / ".agentic" / "config.json"
    data = json.loads(payload.read_text(encoding="utf-8"))
    payload.write_text(
        json.dumps({**data, "control": {"mode": "rules-only"}}, indent=2), encoding="utf-8"
    )

    result = repair.apply(project)

    # The project said it does not want orchestration, so its absence is not a gap to close.
    assert (result["status"], result["repaired"]) == ("PASS", [])
    assert result["readiness"]["execution_readiness"] == "DEGRADED"
    assert not (project / readiness.CONTROL_DIR).exists()


def test_the_command_exits_on_what_is_left(
    project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import argparse

    from agentic_discipline import cli

    monkeypatch.chdir(project)
    _remove(project / readiness.CONTROL_DIR)
    args = argparse.Namespace(dry_run=False, fast=False, json=False)
    assert cli.command_repair(args) == 0
    out = capsys.readouterr().out
    assert "Execution readiness  PARTIAL -> READY" in out
    assert "initialise the control plane" in out

    (project / readiness.STATE_DB).write_bytes(b"not a database")
    assert cli.command_repair(args) == 1
    assert "Left for a person to decide" in capsys.readouterr().out
