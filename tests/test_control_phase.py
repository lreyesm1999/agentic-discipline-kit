"""What `init` does about the control plane, and the mode it records, answer by answer.

The control phase has one answer per situation: refused, skipped for one of two reasons,
pending in a dry run, blocked, adopted or kept. Each is pinned whole here, and so is the
rule that recording a mode touches the payload configuration only when the mode changes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline import bootstrap
from agentic_discipline.bootstrap import initialize_project
from agentic_discipline.common import AgenticError, run_git
from agentic_discipline.readiness import STATE_DB


@pytest.fixture
def root(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='r'\n", encoding="utf-8")
    run_git(["init"], cwd=project)
    return project


def _phase(root: Path, **options: Any) -> tuple[dict[str, Any], list[str]]:
    actions: list[str] = []
    settings = {"mode": "managed", "adopt": None, "rules_only": False, "dry_run": False}
    result = bootstrap._control_phase(root, actions=actions, **{**settings, **options})
    return result, actions


def test_rules_only_on_an_adopted_project_is_refused_and_says_why(root: Path) -> None:
    assert _phase(root, rules_only=True) == (
        {
            "status": "REFUSED",
            "detail": "this project is already adopted, so --rules-only was not recorded:"
            " the existing tasks, leases and evidence stay, and removing .agentic/control"
            " is yours to decide",
            "repair": None,
        },
        [],
    )


def test_a_rules_only_project_and_a_no_adopt_run_are_each_skipped_with_their_repair(
    root: Path,
) -> None:
    assert _phase(root, mode="rules-only", rules_only=True)[0] == {
        "status": "SKIPPED",
        "detail": "installed rules-only, so the control plane was not initialised",
        "repair": "agentic-discipline init --adopt",
    }
    assert _phase(root, adopt=False)[0] == {
        "status": "SKIPPED",
        "detail": "--no-adopt was given, so the control plane was left as it is",
        "repair": "agentic adopt",
    }


def test_a_dry_run_only_says_what_it_would_do(root: Path) -> None:
    assert _phase(root, dry_run=True) == (
        {
            "status": "PENDING",
            "detail": "would adopt the repository and index the project",
            "repair": None,
        },
        [],
    )
    assert not (root / STATE_DB).exists()


def test_adoption_that_cannot_proceed_is_blocked_with_its_reason(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(target: Path) -> None:
        raise AgenticError("an unexplained control directory is in the way")

    monkeypatch.setattr("agentic_discipline.control.plane.adopt", refuse)

    assert _phase(root) == (
        {
            "status": "BLOCKED",
            "detail": "an unexplained control directory is in the way",
            "repair": None,
        },
        [],
    )


def test_a_first_adoption_is_recorded_and_a_second_run_keeps_what_is_there(
    root: Path,
) -> None:
    initialize_project(root, adopt=False)

    assert _phase(root) == (
        {"status": "ADOPTED", "detail": "the repository was adopted and indexed"},
        [f"ADOPT {root / STATE_DB}"],
    )
    (root / "added.py").write_text("x = 1\n", encoding="utf-8")

    result, actions = _phase(root)

    assert result["status"] == "KEPT"
    assert result["detail"].startswith("already adopted; the index was reconciled over ")
    changed = int(result["detail"].split(" over ")[1].split(" ")[0])
    assert changed >= 1
    assert actions == [f"RECONCILE {root / STATE_DB} ({changed} paths)"]


# --- the recorded mode ---------------------------------------------------------------------


def _config(root: Path) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads((root / ".agentic" / "config.json").read_bytes())
    return payload


def test_the_mode_is_recorded_only_when_it_changes(root: Path) -> None:
    initialize_project(root, adopt=False)
    path = root / ".agentic" / "config.json"
    before = _config(root)
    current = before.get("control", {}).get("mode", "managed")
    other = "rules-only" if current == "managed" else "managed"
    actions: list[str] = []

    bootstrap._set_control_mode(root, other, actions, False)
    assert _config(root) == {**before, "control": {"mode": other}}
    assert path.read_bytes().endswith(b"}\n")
    assert actions == [f"UPDATE {path} (control mode {other})"]

    written = path.read_bytes()
    bootstrap._set_control_mode(root, other, actions, False)
    assert path.read_bytes() == written
    assert len(actions) == 1


def test_a_dry_run_reports_the_mode_it_would_record_and_writes_nothing(root: Path) -> None:
    initialize_project(root, adopt=False)
    path = root / ".agentic" / "config.json"
    written = path.read_bytes()

    result = initialize_project(root, rules_only=True, dry_run=True)

    assert path.read_bytes() == written
    assert f"UPDATE {path} (control mode rules-only)" in result["actions"]


def test_a_missing_or_unreadable_payload_configuration_is_left_alone(root: Path) -> None:
    actions: list[str] = []

    bootstrap._set_control_mode(root, "rules-only", actions, False)
    (root / ".agentic").mkdir()
    (root / ".agentic" / "config.json").write_text("not json", encoding="utf-8")
    bootstrap._set_control_mode(root, "rules-only", actions, False)

    assert actions == []
    assert (root / ".agentic" / "config.json").read_text(encoding="utf-8") == "not json"
