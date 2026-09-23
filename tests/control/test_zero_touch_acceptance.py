"""The acceptance tests for zero-touch operation, driven through the public entry points.

Fresh repository, one `init`, one request in natural language: the full workflow, with no
administrative command from the user. Then the two shapes a real repository arrives in -
installed before adoption was part of `init`, and holding a control plane that is broken -
through the same one request.

Each test calls the command lines the way an agent does and nothing else. No task contract,
no `adopt`, no `task ready`, no `agent join`, no `claim`, no `checkpoint`, no "now run the
tests" appears in any of them.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline import cli as installer
from agentic_discipline import readiness
from agentic_discipline.common import run_git
from agentic_discipline.control import cli, work
from agentic_discipline.control.plane import Plane

REQUEST = "Implement a reservations API in src/reservations.py"


def _repository(root: Path) -> Path:
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='r'\nversion='0.1'\n", encoding="utf-8")
    (root / "src" / "reservations.py").write_text(
        "BOOKINGS: dict[str, str] = {}\n", encoding="utf-8"
    )
    (root / "tests" / "test_reservations.py").write_text(
        "def test_ok() -> None:\n    pass\n", encoding="utf-8"
    )
    run_git(["init"], cwd=root)
    return root


def _init(root: Path, **flags: Any) -> int:
    """`npx agentic-discipline init` - the one command a user runs."""

    args = argparse.Namespace(
        target=str(root),
        profile=[],
        profile_file=[],
        force=False,
        max_depth=4,
        adapter=[],
        dry_run=False,
        rules_only=flags.get("rules_only", False),
        no_adopt=flags.get("no_adopt", False),
        adopt=False,
        json=True,
    )
    return installer.command_init(args)


def _keep_gates(root: Path, names: set[str]) -> None:
    """The project keeps the gates whose tools it has, as any project would."""

    path = root / "agentic.config.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    config["gates"] = [
        gate for gate in config["gates"] if isinstance(gate, dict) and gate.get("name") in names
    ]
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")


def _agent(root: Path, action: str, **values: Any) -> dict[str, Any]:
    """What an agent runs on the user's behalf, through the `agentic` command line."""

    args = argparse.Namespace(
        group="work",
        root=root,
        action=action,
        request=values.get("request", ""),
        agent="local-agent",
        capabilities=[],
        no_claim=False,
        session_out=values.get("session_out"),
        task=values.get("task"),
        session_file=values.get("session_file"),
        reason=values.get("reason", "slice_complete"),
        summary=values.get("summary", []),
        next_action=None,
        json=True,
    )
    result = cli.run(args)
    assert result is not None
    return dict(result["data"])


def test_fresh_repository_one_init_one_request_full_workflow(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repository(tmp_path / "fresh")

    # 1. The user runs init once.
    assert _init(root) == 0
    report = json.loads(capsys.readouterr().out)["readiness"]
    assert report["execution_readiness"] == "READY"
    _keep_gates(root, {"python/tests", "python/lint"})

    # 2. The user asks for the work. Everything below is the agent following the rule.
    session_file = tmp_path / "session.json"
    started = _agent(root, "start", request=REQUEST, session_out=session_file)

    # verify installation / verify-adopt the control plane / discover / knowledge
    assert started["preflight"]["mode"] == "FULL"
    # derive-link requirement and task / dependencies / readiness / join and claim
    task = started["task"]
    assert (started["state"], task["state"]) == ("READY", "CLAIMED")
    assert task["objective"] == REQUEST
    assert task["scope"] == ["src/reservations.py"]
    assert task["dependencies"] == []
    assert json.loads(session_file.read_text(encoding="utf-8"))["session"] == started["session"]

    # execute
    (root / "src" / "reservations.py").write_text(
        "BOOKINGS: dict[str, str] = {}\n\n\ndef book(key: str, guest: str) -> None:\n"
        "    BOOKINGS[key] = guest\n",
        encoding="utf-8",
    )

    # checkpoint
    marker = _agent(
        root,
        "checkpoint",
        task=task["id"],
        session_file=session_file,
        summary=["added booking"],
    )
    assert marker["context"]["modified_files"] == ["src/reservations.py"]

    # verify / record evidence / complete
    finished = _agent(root, "finish", task=task["id"], session_file=session_file)
    assert (finished["status"], finished["state"]) == ("PASS", "COMPLETED")
    with Plane(root) as plane:
        evidence = [e for e in plane.store.list("evidence") if e["task_id"] == task["id"]]
        assert {e["kind"] for e in evidence} == {"unit", "static_analysis"}
        assert {e["result"] for e in evidence} == {"PASS"}
        assert plane.store.audit()["status"] == "PASS"


def test_an_installation_from_before_adoption_bootstraps_on_the_first_request(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`.agentic/`, `AGENTS.md` and `agentic.config.json`, but no `state.db`."""

    root = _repository(tmp_path / "legacy")
    _init(root, no_adopt=True)
    capsys.readouterr()
    assert (root / "AGENTS.md").is_file() and (root / ".agentic").is_dir()
    assert not (root / readiness.STATE_DB).exists()
    assert readiness.inspect(root)["execution_readiness"] == "PARTIAL"

    started = _agent(root, "start", request=REQUEST)

    # PARTIAL detected, bootstrapped safely, and the full workflow continued - not the skills
    # alone.
    assert [entry["action"] for entry in started["preflight"]["repaired"]] == [
        "initialise the control plane"
    ]
    assert started["preflight"]["mode"] == "FULL"
    assert started["task"]["state"] == "CLAIMED"
    assert (root / readiness.STATE_DB).is_file()


def test_a_broken_control_plane_blocks_and_is_never_replaced(tmp_path: Path) -> None:
    root = _repository(tmp_path / "broken")
    _init(root)
    database = root / readiness.STATE_DB
    with sqlite3.connect(database) as db:
        db.execute("DROP TRIGGER events_no_update")
        db.execute("UPDATE events SET actor='someone' WHERE seq=(SELECT MIN(seq) FROM events)")
    before = database.read_bytes()

    answer = _agent(root, "start", request=REQUEST)

    assert (answer["status"], answer["mode"]) == ("BLOCKED", "BLOCKED")
    assert "history has been altered" in answer["reason"]
    # No second database, and the first one is exactly as it was found.
    assert sorted(path.name for path in database.parent.glob("*.db")) == ["state.db"]
    assert database.read_bytes() == before


def test_an_unexplained_control_directory_blocks_the_request(tmp_path: Path) -> None:
    root = _repository(tmp_path / "unexplained")
    _init(root, no_adopt=True)
    (root / readiness.CONTROL_DIR).mkdir(parents=True)

    answer = _agent(root, "start", request=REQUEST)

    assert answer["mode"] == "BLOCKED"
    assert "split the project's history" in answer["reason"]
    assert list((root / readiness.CONTROL_DIR).iterdir()) == []


def test_a_rules_only_project_says_it_cannot_run_the_workflow(tmp_path: Path) -> None:
    """Degraded is never hidden: the request that needs orchestration is refused by name."""

    from agentic_discipline.control.contracts import ControlError

    root = _repository(tmp_path / "rules")
    _init(root, rules_only=True)

    with pytest.raises(ControlError, match="needs the full workflow"):
        _agent(root, "start", request=REQUEST)
    assert not (root / readiness.STATE_DB).exists()


def test_the_rule_the_agent_follows_is_the_one_every_surface_carries() -> None:
    """One canonical rule, compiled to every adapter, so no surface can drift from it."""

    from agentic_discipline.adapters import ADAPTERS, sync_adapters
    from agentic_discipline.bootstrap import find_contract_root
    from agentic_discipline.skills import load_disciplines

    discipline = next(
        item
        for item in load_disciplines(find_contract_root())
        if item.id == "autonomous-project-execution"
    )
    for line in (
        "THEN verify operational readiness first",
        "NEVER continue silently without the control plane",
        "`agentic preflight`",
        '`agentic work start "<request>"`',
    ):
        assert line in discipline.body
    assert set(ADAPTERS) >= {"claude", "cursor", "copilot", "windsurf", "gemini", "generic"}
    assert work.CHECKPOINT_REASONS[0] == "slice_complete"
    assert callable(sync_adapters)
