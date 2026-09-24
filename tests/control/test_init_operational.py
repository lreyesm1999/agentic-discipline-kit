"""`init` leaves a project operational, and leaves existing work alone.

One command has to produce a project that can actually run the workflow, or the user is
left deciding between `adopt`, `reconcile` and `task create` without being told. These tests
cover the shapes a real repository arrives in: fresh, installed by an older release,
already adopted, mid-task, or holding a control directory nobody can explain.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from conftest import checkpoint, contract

from agentic_discipline import readiness
from agentic_discipline.bootstrap import initialize_project
from agentic_discipline.common import run_git
from agentic_discipline.control.plane import Plane


@pytest.fixture
def fresh(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (root / "app.py").write_text("value = 1\n", encoding="utf-8")
    (root / "test_app.py").write_text("import app\n", encoding="utf-8")
    run_git(["init"], cwd=root)
    return root


def _state(root: Path) -> tuple[int, int]:
    """The audit length and the entity count: what a second run must not disturb."""

    from agentic_discipline.control.store import Store

    store = Store(root / readiness.STATE_DB)
    try:
        return store.audit()["records"], len(store.list("entity"))
    finally:
        store.close()


def test_one_init_leaves_a_fresh_project_ready(fresh: Path) -> None:
    result = initialize_project(fresh)
    assert result["control"]["status"] == "ADOPTED"
    assert result["control_mode"] == "managed"
    assert result["readiness"]["execution_readiness"] == "READY"
    # The project is adopted, indexed and has an execution policy, with no further commands.
    assert (fresh / readiness.STATE_DB).is_file()
    for name in ("control_plane", "project_adoption", "knowledge", "task_orchestration"):
        check = next(c for c in result["readiness"]["checks"] if c["name"] == name)
        assert check["status"] == "PASS"


def test_running_init_again_changes_nothing(fresh: Path) -> None:
    initialize_project(fresh)
    before = _state(fresh)
    result = initialize_project(fresh)
    assert result["control"]["status"] == "KEPT"
    assert "0 changed path(s)" in result["control"]["detail"]
    assert _state(fresh) == before
    assert result["readiness"]["execution_readiness"] == "READY"


def test_init_preserves_tasks_leases_checkpoints_and_evidence(fresh: Path) -> None:
    initialize_project(fresh)
    with Plane(fresh) as plane:
        data = contract()
        plane.approve_command(data["verification"][0]["command"])
        task = plane.create_task(data)
        plane.ready(task["id"])
        session = plane.join("worker", ["code"])["session"]
        plane.claim(task["id"], session)
        plane.checkpoint(task["id"], session, checkpoint())
        before = plane.store.get(task["id"], "task")
        checkpoints = len(plane.store.list("checkpoint"))

    initialize_project(fresh)

    with Plane(fresh) as plane:
        after = plane.store.get(task["id"], "task")
        assert after == before
        assert len(plane.store.list("checkpoint")) == checkpoints
        assert len(plane.store.list("lease")) == 1


def test_init_reindexes_a_tree_that_moved_on(fresh: Path) -> None:
    initialize_project(fresh)
    (fresh / "feature.py").write_text("def added() -> int:\n    return 2\n", encoding="utf-8")
    result = initialize_project(fresh)
    assert result["control"]["status"] == "KEPT"
    assert "0 changed path(s)" not in result["control"]["detail"]
    assert result["readiness"]["drift"] == []
    with Plane(fresh) as plane:
        paths = {e["path"] for e in plane.store.list("entity") if e.get("path")}
    assert "feature.py" in paths


def test_a_project_installed_by_an_older_release_is_completed_in_place(fresh: Path) -> None:
    """The legacy shape: payload, AGENTS.md and config, but no control plane at all."""

    initialize_project(fresh, adopt=False)
    assert not (fresh / readiness.CONTROL_DIR).exists()
    partial = readiness.inspect(fresh)
    assert partial["execution_readiness"] == "PARTIAL"

    result = initialize_project(fresh)
    assert result["control"]["status"] == "ADOPTED"
    assert result["readiness"]["execution_readiness"] == "READY"


def test_no_adopt_skips_this_run_without_recording_a_choice(fresh: Path) -> None:
    result = initialize_project(fresh, adopt=False)
    assert result["control"] == {
        "status": "SKIPPED",
        "detail": "--no-adopt was given, so the control plane was left as it is",
        "repair": "agentic adopt",
    }
    # Nothing was recorded, so the next ordinary run adopts.
    assert result["control_mode"] == "managed"
    assert initialize_project(fresh)["control"]["status"] == "ADOPTED"


def test_rules_only_is_recorded_and_survives_an_ordinary_rerun(fresh: Path) -> None:
    result = initialize_project(fresh, rules_only=True)
    assert result["control"]["status"] == "SKIPPED"
    assert result["control_mode"] == "rules-only"
    assert result["readiness"]["execution_readiness"] == "DEGRADED"
    payload = json.loads((fresh / ".agentic" / "config.json").read_text(encoding="utf-8"))
    assert payload["control"] == {"mode": "rules-only"}

    # A routine re-run must not turn orchestration on behind the owner's back.
    again = initialize_project(fresh)
    assert (again["control_mode"], again["control"]["status"]) == ("rules-only", "SKIPPED")
    assert again["control"]["repair"] == "agentic-discipline init --adopt"

    asked = initialize_project(fresh, adopt=True)
    assert (asked["control_mode"], asked["control"]["status"]) == ("managed", "ADOPTED")


def test_rules_only_cannot_un_adopt_a_project(fresh: Path) -> None:
    initialize_project(fresh)
    with Plane(fresh) as plane:
        task = plane.create_task(contract())

    result = initialize_project(fresh, rules_only=True)

    assert result["control"]["status"] == "REFUSED"
    assert result["control_mode"] == "managed"
    assert "yours to decide" in result["control"]["detail"]
    payload = json.loads((fresh / ".agentic" / "config.json").read_text(encoding="utf-8"))
    assert payload["control"] == {"mode": "managed"}
    with Plane(fresh) as plane:
        assert plane.store.get(task["id"], "task")["id"] == task["id"]


def test_an_unexplained_control_directory_stops_the_bootstrap(fresh: Path) -> None:
    (fresh / readiness.CONTROL_DIR).mkdir(parents=True)
    result = initialize_project(fresh)
    assert result["control"]["status"] == "BLOCKED"
    assert "inspect it before adoption" in result["control"]["detail"]
    assert result["readiness"]["execution_readiness"] == "BROKEN"
    # The rules are installed and the directory is untouched: no second database beside it.
    assert (fresh / "AGENTS.md").is_file()
    assert list((fresh / readiness.CONTROL_DIR).iterdir()) == []


def test_init_works_on_a_repository_without_git(tmp_path: Path) -> None:
    """Adoption falls back to walking the tree, so the order of init and `git init` is free."""

    root = tmp_path / "nogit"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    result = initialize_project(root)
    assert result["control"]["status"] == "ADOPTED"
    git = next(c for c in result["readiness"]["checks"] if c["name"] == "git_integration")
    assert (git["status"], git["repair"]) == ("MISSING", "git init")

    run_git(["init"], cwd=root)
    assert readiness.inspect(root)["execution_readiness"] == "READY"


def test_a_dry_run_writes_nothing_and_says_what_it_would_do(fresh: Path) -> None:
    result = initialize_project(fresh, dry_run=True)
    assert result["control"] == {
        "status": "PENDING",
        "detail": "would adopt the repository and index the project",
        "repair": None,
    }
    assert result["readiness"] is None
    assert not (fresh / readiness.CONTROL_DIR).exists()
    assert not (fresh / ".agentic" / "config.json").exists()


def test_adapters_are_regenerated_by_a_rerun(fresh: Path) -> None:
    initialize_project(fresh)
    (fresh / "AGENTS.md").write_text("# replaced by hand\n", encoding="utf-8")
    result = initialize_project(fresh)
    body = (fresh / "AGENTS.md").read_text(encoding="utf-8")
    assert "Agentic Discipline" in body
    assert result["readiness"]["execution_readiness"] == "READY"


def test_init_does_not_disturb_a_git_worktree(fresh: Path) -> None:
    initialize_project(fresh)
    run_git(["add", "-A"], cwd=fresh)
    run_git(["-c", "user.email=t@e", "-c", "user.name=t", "commit", "-qm", "first"], cwd=fresh)
    head = run_git(["rev-parse", "HEAD"], cwd=fresh).strip()
    tree = run_git(["worktree", "list"], cwd=fresh).strip()

    initialize_project(fresh)

    assert run_git(["rev-parse", "HEAD"], cwd=fresh).strip() == head
    assert run_git(["worktree", "list"], cwd=fresh).strip() == tree


def _flags(**values: Any) -> Any:
    import argparse

    from agentic_discipline import cli

    defaults = dict(
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
    return cli, argparse.Namespace(**{**defaults, **values})


def test_the_command_exits_nonzero_when_the_install_is_not_usable(
    fresh: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli, args = _flags(target=str(fresh))
    assert cli.command_init(args) == 0
    assert json.loads(capsys.readouterr().out)["readiness"]["execution_readiness"] == "READY"

    (fresh / readiness.STATE_DB).write_bytes(b"not a database")
    cli, args = _flags(target=str(fresh))
    assert cli.command_init(args) == 1
    assert json.loads(capsys.readouterr().out)["readiness"]["execution_readiness"] == "BROKEN"
