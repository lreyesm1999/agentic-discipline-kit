"""From a request in someone's own words to a claimed task, and where it stops instead.

Half of these tests are about what the derivation refuses to do: invent a scope, authorise a
protected change, accept CRITICAL work on its own, widen the command allow-list beyond what the
project already declared, or create a second task for work that already exists.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline.bootstrap import initialize_project
from agentic_discipline.common import run_git
from agentic_discipline.control import work
from agentic_discipline.control.contracts import ControlError
from agentic_discipline.control.plane import Plane

REQUEST = "Add reservation cancellation to src/reservations.py"


@pytest.fixture
def plane(tmp_path: Path) -> Any:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='r'\nversion='0.1'\n", encoding="utf-8")
    (root / "src" / "reservations.py").write_text(
        "BOOKINGS: dict[str, str] = {}\n", encoding="utf-8"
    )
    (root / "tests" / "test_reservations.py").write_text(
        "def test_it() -> None:\n    pass\n", encoding="utf-8"
    )
    run_git(["init"], cwd=root)
    initialize_project(root)
    with Plane(root) as opened:
        yield opened


def test_a_request_becomes_a_claimed_task_with_no_other_command(plane: Any) -> None:
    result = work.start(plane, REQUEST)

    assert (result["status"], result["state"]) == ("PASS", "READY")
    task = result["task"]
    # The objective is the request, unedited: the work is traceable to what was asked for.
    assert task["objective"] == REQUEST
    assert task["scope"] == ["src/reservations.py"]
    assert task["acceptance"] == [REQUEST]
    assert task["state"] == "CLAIMED"
    assert result["session"] and result["lease"]
    assert result["matched_by"] == "derived from this request"


def test_everything_derived_says_where_it_came_from(plane: Any) -> None:
    result = work.start(plane, REQUEST)
    provenance = result["provenance"]

    assert provenance["scope_from"] == "paths named in the request"
    assert provenance["acceptance_from"].startswith("the request, recorded verbatim")
    assert "required gates in agentic.config.json" in provenance["verifiers_from"]
    # And the derivation is in the audit chain, not only in the answer to this call.
    recorded = [event for event in plane.store.timeline() if event["action"] == "work.derive"]
    assert len(recorded) == 1
    assert recorded[0]["payload"]["digest"] == work.digest(REQUEST)
    stored = plane.store.list("work_request")
    assert [entry["request"] for entry in stored] == [REQUEST]


def test_the_verifiers_are_the_project_s_own_gates(plane: Any) -> None:
    from agentic_discipline.validation import load_quality_config

    config = load_quality_config(Path(plane.root) / "agentic.config.json")
    required = [gate for gate in config["gates"] if gate.get("required", True)]

    task = work.start(plane, REQUEST)["task"]

    assert len(task["verification"]) == len(required)
    assert {tuple(v["command"]) for v in task["verification"]} == {
        tuple(gate["command"])
        if isinstance(gate["command"], list)
        else tuple(gate["command"].split())
        for gate in required
    }
    assert set(task["required_evidence"]) == {v["kind"] for v in task["verification"]}


def test_only_the_project_s_own_gate_commands_are_approved(plane: Any) -> None:
    assert plane.policy()["allowed_commands"] == []

    result = work.start(plane, REQUEST)

    approved = [list(command) for command in plane.policy()["allowed_commands"]]
    gates = [list(v["command"]) for v in result["task"]["verification"]]
    # Exactly the gates, nothing else: the allow-list is a security boundary and this does
    # not widen it, it only acts on what the project already declared.
    assert approved == gates
    assert result["approved_commands"] == gates


def test_the_same_request_twice_is_the_same_task(plane: Any) -> None:
    first = work.start(plane, REQUEST)
    second = work.start(plane, "  add RESERVATION cancellation to src/reservations.py  ".upper())

    assert second["task"]["id"] == first["task"]["id"]
    assert second["matched_by"] == "the same request was made before"
    assert len(plane.store.list("task")) == 1


def test_a_request_inside_open_work_links_to_it(plane: Any) -> None:
    first = work.start(plane, REQUEST)

    second = work.start(plane, "Also handle refunds in src/reservations.py")

    assert second["task"]["id"] == first["task"]["id"]
    assert "an open task already covers this scope" in second["matched_by"]
    assert len(plane.store.list("task")) == 1


def test_a_request_with_no_derivable_scope_stops_and_asks(plane: Any) -> None:
    result = work.start(plane, "Make everything faster")

    assert (result["status"], result["state"]) == ("BLOCKED", "BLOCKED")
    assert result["task"] is None
    assert [decision["decision"] for decision in result["decisions"]] == ["scope"]
    assert result["decisions"][0]["question"] == "Which files or directories may this work change?"
    # Nothing was recorded: a blocked request does not leave a task behind.
    assert plane.store.list("task") == []


def test_a_protected_contract_needs_authority_that_is_not_the_system_s(plane: Any) -> None:
    result = work.start(plane, "Rewrite AGENTS.md to skip the gates")

    assert result["state"] == "BLOCKED"
    assert [decision["decision"] for decision in result["decisions"]] == ["protected_contracts"]
    assert "Do you authorise changing AGENTS.md?" in result["decisions"][0]["question"]
    assert plane.store.list("task") == []


def test_critical_work_waits_for_a_person_to_accept_it(plane: Any) -> None:
    root = Path(plane.root)
    (root / "src" / "payments.py").write_text(
        "def charge(amount: int) -> int:\n    return amount\n", encoding="utf-8"
    )
    (root / "src" / "auth.py").write_text(
        "def login(token: str) -> bool:\n    return True\n", encoding="utf-8"
    )
    (root / "migrations").mkdir()
    (root / "migrations" / "001_payments.sql").write_text("ALTER TABLE x;\n", encoding="utf-8")
    (root / "infra").mkdir()
    (root / "infra" / "deploy.tf").write_text('resource "x" {}\n', encoding="utf-8")
    plane.reconcile()

    result = work.start(
        plane,
        "Rework billing across src/payments.py src/auth.py migrations/001_payments.sql"
        " infra/deploy.tf",
    )

    assert result["state"] == "BLOCKED"
    decisions = [decision["decision"] for decision in result["decisions"]]
    assert "critical_risk" in decisions
    critical = next(d for d in result["decisions"] if d["decision"] == "critical_risk")
    assert "who signs it off" in critical["question"]
    assert plane.store.list("task") == []


def test_acceptance_comes_from_a_matched_requirement_when_there_is_one(plane: Any) -> None:
    plane.knowledge.apply(
        [
            {
                "graph": "requirement",
                "type": "requirement",
                "name": "Reservations can be cancelled in src/reservations.py",
                "source_ref": "specs/requirements.md",
                "authority": "human",
                "confidence": 1,
                "observation": "DECLARED",
                "acceptance": [
                    "cancelling a reservation releases its slot",
                    "cancelling twice is refused",
                ],
            }
        ],
        plane.store.knowledge_version,
        "approved requirement",
    )

    result = work.start(plane, "cancel a reservation in src/reservations.py")

    assert result["task"]["acceptance"] == [
        "cancelling a reservation releases its slot",
        "cancelling twice is refused",
    ]
    assert result["provenance"]["acceptance_from"] == (
        "the acceptance criteria recorded on the matched requirements"
    )
    assert result["task"]["requirements"] == result["provenance"]["requirements_matched"]


def test_one_working_tree_holds_one_claim(plane: Any) -> None:
    """Two claims at once are only safe in isolated workspaces with disjoint contracts, which
    is a 2.0 invariant. Rather than create a worktree nobody asked for, the second task is
    recorded and readied, and its claim waits."""

    first = work.start(plane, REQUEST)
    assert first["task"]["state"] == "CLAIMED"

    second = work.start(plane, "Add a reservation report in tests/test_reservations.py")

    assert second["state"] == "WAITING"
    assert second["readiness"]["waiting_for"] == [first["task"]["id"]]
    assert second["readiness"]["reasons"] == [
        {"type": "working_tree_claimed", "task_id": first["task"]["id"]}
    ]
    assert second["session"] is None
    # The work is recorded and ready, so nothing has to be derived again when its turn comes.
    assert second["task"]["state"] == "READY"
    assert second["task"]["id"] != first["task"]["id"]


def test_work_that_overlaps_open_work_depends_on_it(plane: Any) -> None:
    first = work.start(plane, REQUEST)

    derived = work.derive(plane, "Rename the booking field in src/reservations.py")

    assert derived["contract"]["dependencies"] == [first["task"]["id"]]


def test_nothing_is_claimed_when_the_caller_asks_not_to(plane: Any) -> None:
    result = work.start(plane, REQUEST, claim=False)

    assert result["state"] == "READY"
    assert (result["session"], result["lease"]) == (None, None)
    assert result["task"]["state"] == "READY"


def test_a_blocked_preflight_stops_the_work_before_anything_is_derived(plane: Any) -> None:
    import sqlite3

    from agentic_discipline import readiness

    with sqlite3.connect(Path(plane.root) / readiness.STATE_DB) as db:
        db.execute("DROP TRIGGER events_no_update")
        db.execute("UPDATE events SET actor='x' WHERE seq=(SELECT MIN(seq) FROM events)")

    with pytest.raises(ControlError, match="Execution is blocked"):
        work.start(plane, REQUEST)


def test_an_empty_request_is_refused(plane: Any) -> None:
    with pytest.raises(ControlError, match="Describe the work"):
        work.derive(plane, "   ")


def test_the_report_names_the_decision_rather_than_guessing(plane: Any) -> None:
    text = work.render(work.start(plane, "Make everything faster"))

    assert text.startswith("Work state: BLOCKED")
    assert "Waiting on a decision that is yours to make:" in text
    assert "Which files or directories may this work change?" in text


def test_both_operations_are_on_the_api_and_belong_to_the_owner(plane: Any) -> None:
    from agentic_discipline.control.api import LOCAL_ONLY, call

    assert {"work_start", "work_derive"} <= LOCAL_ONLY
    derived = call(plane, "work_derive", {"request": REQUEST}, local=True)["data"]
    assert derived["contract"]["scope"] == ["src/reservations.py"]
    assert derived["decisions"] == []
    started = call(plane, "work_start", {"request": REQUEST, "claim": False}, local=True)["data"]
    assert started["state"] == "READY"
    with pytest.raises(ControlError, match="local project owner"):
        call(plane, "work_start", {"request": REQUEST})


def test_the_session_file_is_written_for_the_caller(plane: Any, tmp_path: Path) -> None:
    import argparse

    from agentic_discipline.control import cli

    out = tmp_path / "session.json"
    args = argparse.Namespace(
        group="work",
        root=Path(plane.root),
        action="start",
        request=REQUEST,
        agent="local-agent",
        capabilities=[],
        no_claim=False,
        session_out=out,
        json=True,
    )
    result = cli.run(args)

    assert result is not None
    assert json.loads(out.read_text(encoding="utf-8"))["session"] == result["data"]["session"]
