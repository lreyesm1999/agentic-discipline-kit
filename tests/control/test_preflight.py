"""The preflight every real execution starts with, in all three modes.

What is being pinned is mostly what the report refuses to do: claim a full workflow it does
not have, hide a degraded one, repeat one absence as several problems, or let an operation
that needs orchestration run without it.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline import readiness
from agentic_discipline.bootstrap import initialize_project
from agentic_discipline.common import run_git
from agentic_discipline.control import preflight
from agentic_discipline.control.contracts import ControlError
from agentic_discipline.control.plane import Plane


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    run_git(["init"], cwd=root)
    initialize_project(root)
    return root


def _remove(path: Path) -> None:
    for child in sorted(path.rglob("*"), reverse=True):
        child.unlink() if child.is_file() else child.rmdir()
    path.rmdir()


def _requirement(result: dict[str, Any], name: str) -> dict[str, Any]:
    return next(item for item in result["requirements"] if item["requirement"] == name)


def test_an_adopted_project_is_full_and_names_every_requirement(project: Path) -> None:
    result = preflight.run(project)
    assert (result["mode"], result["status"]) == ("FULL", "PASS")
    assert [item["requirement"] for item in result["requirements"]] == [
        "installation",
        "version",
        "control_plane",
        "adoption",
        "knowledge",
        "git",
        "quality_configuration",
        "task_orchestration",
    ]
    assert {item["status"] for item in result["requirements"]} == {"PASS"}
    assert (result["unavailable"], result["safe_to_proceed"]) == ([], True)


def test_a_missing_control_plane_is_repaired_before_the_work_starts(project: Path) -> None:
    _remove(project / readiness.CONTROL_DIR)

    result = preflight.run(project)

    assert result["mode"] == "FULL"
    assert [entry["action"] for entry in result["repaired"]] == ["initialise the control plane"]
    assert (project / readiness.STATE_DB).is_file()


def test_nothing_is_repaired_when_the_caller_only_wants_the_report(project: Path) -> None:
    _remove(project / readiness.CONTROL_DIR)

    result = preflight.run(project, repair_first=False)

    assert (result["mode"], result["repaired"]) == ("BLOCKED", [])
    assert not (project / readiness.CONTROL_DIR).exists()
    # A gap that a repair would have closed is still a blocker while it is open: the work
    # cannot proceed as though the workflow were there.
    assert _requirement(result, "control_plane")["status"] == "MISSING"


def test_a_rules_only_project_is_degraded_and_says_what_is_gone(project: Path) -> None:
    _remove(project / readiness.CONTROL_DIR)
    payload = project / ".agentic" / "config.json"
    data = json.loads(payload.read_text(encoding="utf-8"))
    payload.write_text(
        json.dumps({**data, "control": {"mode": "rules-only"}}, indent=2), encoding="utf-8"
    )

    result = preflight.run(project)

    assert (result["mode"], result["safe_to_proceed"]) == ("DEGRADED", True)
    assert "on purpose" in result["reason"]
    # The point of the mode is that nothing is left implied.
    assert result["unavailable"] == list(preflight.ORCHESTRATION)
    assert result["status"] == "FAIL"


def test_unexplained_state_blocks_and_is_not_touched(project: Path) -> None:
    _remove(project / readiness.CONTROL_DIR)
    (project / readiness.CONTROL_DIR).mkdir(parents=True)

    result = preflight.run(project)

    assert (result["mode"], result["safe_to_proceed"]) == ("BLOCKED", False)
    assert "split the project's history" in result["reason"]
    assert list((project / readiness.CONTROL_DIR).iterdir()) == []


def test_an_altered_history_blocks(project: Path) -> None:
    with sqlite3.connect(project / readiness.STATE_DB) as db:
        db.execute("DROP TRIGGER events_no_update")
        db.execute("UPDATE events SET actor='someone' WHERE seq=(SELECT MIN(seq) FROM events)")

    result = preflight.run(project)

    assert result["mode"] == "BLOCKED"
    assert _requirement(result, "control_plane")["status"] == "FAIL"


def test_a_project_installed_by_a_newer_kit_blocks_rather_than_downgrading(project: Path) -> None:
    payload = project / ".agentic" / "config.json"
    data = json.loads(payload.read_text(encoding="utf-8"))
    payload.write_text(json.dumps({**data, "schema_version": "99"}, indent=2), encoding="utf-8")

    result = preflight.run(project)

    version = _requirement(result, "version")
    assert (result["mode"], version["status"]) == ("BLOCKED", "FAIL")
    assert "upgrade the kit" in version["detail"]


def test_leftovers_from_an_older_layout_do_not_hold_up_the_work(project: Path) -> None:
    """The payload under `.agentic/` is what is read. Deleting the old copies is the owner's
    call, so the leftovers are reported with the command that clears them and nothing else."""

    (project / "MASTER_PROMPT.md").write_text("# legacy copy\n", encoding="utf-8")

    result = preflight.run(project)

    version = _requirement(result, "version")
    assert (result["mode"], version["status"], version["advisory"]) == ("FULL", "STALE", True)
    assert version["repair"] == "agentic-discipline migrate --prune"
    assert (project / "MASTER_PROMPT.md").is_file()


def test_a_payload_from_an_older_release_stops_the_work(project: Path) -> None:
    payload = project / ".agentic" / "config.json"
    data = json.loads(payload.read_text(encoding="utf-8"))
    payload.write_text(json.dumps({**data, "schema_version": "2"}, indent=2), encoding="utf-8")

    result = preflight.run(project)

    version = _requirement(result, "version")
    assert (result["mode"], version["status"]) == ("BLOCKED", "FAIL")
    assert "agentic-discipline migrate" in version["detail"]


def test_a_project_without_git_runs_but_loses_what_needs_a_commit(tmp_path: Path) -> None:
    root = tmp_path / "nogit"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    initialize_project(root)

    result = preflight.run(root)

    assert (result["mode"], result["safe_to_proceed"]) == ("FULL", True)
    assert result["unavailable"] == list(preflight.NEEDS_GIT)
    with pytest.raises(ControlError, match="needs a git working tree"):
        preflight.requires(result, git=True)


def test_one_absence_is_reported_once(project: Path) -> None:
    _remove(project / readiness.CONTROL_DIR)
    (project / readiness.CONTROL_DIR).mkdir(parents=True)

    text = preflight.render(preflight.run(project))

    # Adoption, knowledge and orchestration are all missing because the plane is, and the
    # cause is already stated; listing them again would read as four problems.
    assert text.count("Outstanding:") == 1
    outstanding = text.split("Outstanding:")[1]
    assert "control_plane (FAIL)" in outstanding
    for consequence in ("adoption (", "knowledge (", "task_orchestration ("):
        assert consequence not in outstanding


def test_the_rendered_report_never_hides_a_degraded_mode(project: Path) -> None:
    _remove(project / readiness.CONTROL_DIR)
    payload = project / ".agentic" / "config.json"
    data = json.loads(payload.read_text(encoding="utf-8"))
    payload.write_text(
        json.dumps({**data, "control": {"mode": "rules-only"}}, indent=2), encoding="utf-8"
    )

    text = preflight.render(preflight.run(project))

    assert text.startswith("Execution mode: DEGRADED")
    assert "Unavailable:" in text
    assert "the completion invariant" in text
    assert text.endswith("Proceeding is safe for the work this mode supports.")


def test_work_that_needs_orchestration_is_refused_in_a_degraded_mode(project: Path) -> None:
    _remove(project / readiness.CONTROL_DIR)
    payload = project / ".agentic" / "config.json"
    data = json.loads(payload.read_text(encoding="utf-8"))
    payload.write_text(
        json.dumps({**data, "control": {"mode": "rules-only"}}, indent=2), encoding="utf-8"
    )
    result = preflight.run(project)

    with pytest.raises(ControlError, match="needs the full workflow"):
        preflight.requires(result)
    # And work that only needs the rules is allowed to say so.
    preflight.requires(result, orchestration=False)


def test_blocked_refuses_everything(project: Path) -> None:
    _remove(project / readiness.CONTROL_DIR)
    (project / readiness.CONTROL_DIR).mkdir(parents=True)
    result = preflight.run(project)

    with pytest.raises(ControlError, match="Execution is blocked"):
        preflight.requires(result, orchestration=False)


def test_the_operation_is_reachable_through_the_api_and_belongs_to_the_owner(
    project: Path,
) -> None:
    from agentic_discipline.control.api import LOCAL_ONLY, call

    assert "preflight" in LOCAL_ONLY
    with Plane(project) as plane:
        result = call(plane, "preflight", {"repair": False, "deep": False}, local=True)
        assert result["data"]["mode"] == "FULL"
        with pytest.raises(ControlError, match="local project owner"):
            call(plane, "preflight", {}, local=False)
