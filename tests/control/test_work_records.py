"""The records work derivation writes and returns, whole.

Everything `work` produces is read by someone: the contract becomes the task, the provenance
is the audit trail of why, the decisions are the questions a person answers, and the report
is what the agent acts on. Each is pinned entire, so a renamed key, a changed message or a
budget that drifted is a failing test rather than a silent change.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline.bootstrap import initialize_project
from agentic_discipline.common import run_git
from agentic_discipline.control import work
from agentic_discipline.control.contracts import ControlError
from agentic_discipline.control.plane import Plane

REQUEST = "Add a total to src/app.py"
GATE = [sys.executable, "-c", "pass"]


def _gates(root: Path, gates: list[dict[str, Any]]) -> None:
    path = root / "agentic.config.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    config["gates"] = gates
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")


@pytest.fixture
def plane(tmp_path: Path) -> Any:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\nname='r'\nversion='0.1'\n", encoding="utf-8")
    (root / "src" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "src" / "other.py").write_text("OTHER = 2\n", encoding="utf-8")
    run_git(["init"], cwd=root)
    initialize_project(root)
    _gates(root, [{"name": "python/tests", "command": GATE}])
    with Plane(root) as opened:
        opened.reconcile()
        yield opened


def _verifier() -> dict[str, Any]:
    return {"kind": "unit", "command": GATE, "acceptance": [0]}


def test_the_derived_contract_and_its_provenance_are_exactly_these(plane: Any) -> None:
    derived = work.derive(plane, f"  {REQUEST}  ")

    assert derived == {
        "contract": {
            "objective": REQUEST,
            "scope": ["src/app.py"],
            "out_of_scope": ["anything outside the recorded scope", "protected contracts"],
            "requirements": [],
            "acceptance": [REQUEST],
            "dependencies": [],
            "boundaries": [],
            "context": [
                f"request digest {work.digest(REQUEST)}",
                "acceptance from the request, recorded verbatim because nothing else states it",
            ],
            "verification": [_verifier()],
            "required_evidence": ["unit"],
            "rollback": "revert the changes this task made to its scope; nothing outside it was"
            " authorised, and no deployment or migration is part of this task",
            "definition_of_done": "every acceptance criterion has current passing evidence and a"
            " checkpoint records the work",
            "risk": "LOW",
            "budget": {
                "max_runtime": 1800,
                "max_retries": 3,
                "max_files": 4,
                "max_lines": 2000,
                "max_external_calls": 0,
                "max_cost": 0,
            },
        },
        "decisions": [],
        "provenance": {
            "request": REQUEST,
            "digest": work.digest(REQUEST),
            "scope_from": "paths named in the request",
            "acceptance_from": "the request, recorded verbatim because nothing else states it",
            "verifiers_from": "the 1 required gates in agentic.config.json",
            "requirements_matched": [],
            "risk_signals": [],
        },
    }


def test_the_file_budget_grows_with_the_scope(plane: Any) -> None:
    derived = work.derive(plane, "Share a constant between src/app.py and src/other.py")

    assert derived["contract"]["scope"] == ["src/app.py", "src/other.py"]
    assert derived["contract"]["budget"]["max_files"] == 4
    (Path(plane.root) / "src" / "third.py").write_text("THIRD = 3\n", encoding="utf-8")
    plane.reconcile()
    wide = work.derive(plane, "Rename across src/app.py src/other.py src/third.py")
    assert wide["contract"]["budget"]["max_files"] == 6


def test_each_decision_the_system_will_not_make_is_worded_exactly(plane: Any) -> None:
    assert work.derive(plane, "Make everything faster")["decisions"] == [
        {
            "decision": "scope",
            "question": "Which files or directories may this work change?",
            "why": "nothing in the request names a path, and the project's index does not"
            " associate its words with any file, so there is no bounded scope to authorise",
        }
    ]
    assert work.derive(plane, "Rewrite AGENTS.md and agentic.config.json")["decisions"] == [
        {
            "decision": "protected_contracts",
            "question": "Do you authorise changing AGENTS.md, agentic.config.json?",
            "why": "these are protected contracts, and only a contract-authorised role may"
            " change them",
        }
    ]


def test_critical_risk_names_the_signals_that_made_it_critical(plane: Any) -> None:
    root = Path(plane.root)
    for name in ("src/payments.py", "src/auth.py", "migrations/001.sql", "infra/deploy.tf"):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text("x = 1\n", encoding="utf-8")
    plane.reconcile()

    derived = work.derive(
        plane, "Rework src/payments.py src/auth.py migrations/001.sql infra/deploy.tf"
    )

    (critical,) = [d for d in derived["decisions"] if d["decision"] == "critical_risk"]
    signals = derived["provenance"]["risk_signals"]
    assert signals
    assert critical == {
        "decision": "critical_risk",
        "question": "Do you accept this as CRITICAL work, and who signs it off?",
        "why": "the project's own risk rules classify this scope as CRITICAL, which"
        f" requires explicit human acceptance: {', '.join(signals)}",
    }


def test_an_empty_request_is_refused_with_its_code(plane: Any) -> None:
    with pytest.raises(ControlError) as refused:
        work.derive(plane, "   ")

    assert (refused.value.code, str(refused.value)) == (
        "INVALID_REQUEST",
        "Describe the work in your own words",
    )


def test_a_blocked_request_answers_with_exactly_this(plane: Any) -> None:
    answer = work.start(plane, "Make everything faster")

    flight = answer.pop("preflight")
    assert flight["mode"] == "FULL"
    assert answer == {
        "status": "BLOCKED",
        "state": "BLOCKED",
        "request": "Make everything faster",
        "task": None,
        "decisions": work.derive(plane, "Make everything faster")["decisions"],
        "provenance": work.derive(plane, "Make everything faster")["provenance"],
        "reason": "this work needs a decision that is not the system's to make",
    }


def test_a_derived_task_leaves_its_request_record_and_audit_event(plane: Any) -> None:
    answer = work.start(plane, REQUEST)
    task = answer["task"]["id"]

    (record,) = plane.store.list("work_request")
    created = record.pop("created_at")
    record.pop("id")
    record.pop("version")
    assert isinstance(created, float)
    assert record == {
        "task_id": task,
        "request": REQUEST,
        "digest": work.digest(REQUEST),
        "provenance": answer["provenance"],
    }
    (event,) = [e for e in plane.store.timeline() if e["action"] == "work.derive"]
    assert event["actor"] == "local-owner"
    assert event["payload"] == {
        "task": task,
        "digest": work.digest(REQUEST),
        **answer["provenance"],
    }


def test_the_ready_report_is_exactly_this(plane: Any) -> None:
    answer = work.start(plane, REQUEST)

    assert (answer["status"], answer["state"]) == ("PASS", "READY")
    assert answer["readiness"] == {"state": "READY", "reasons": [], "waiting_for": []}
    assert answer["reason"] == "the task is claimed and the work may proceed"
    assert answer["request"] == REQUEST
    assert answer["approved_commands"] == [GATE]
    assert answer["matched_by"] == "derived from this request"
    # The agent registered under the default name, with the default capability.
    (agent,) = plane.store.list("agent")
    assert (agent["name"], agent["capabilities"]) == ("local-agent", ["code"])


def test_a_task_waiting_for_the_working_tree_says_whose_it_is(plane: Any) -> None:
    first = work.start(plane, REQUEST)["task"]["id"]

    second = work.start(plane, "Add a subtotal to src/other.py")

    assert (second["status"], second["state"]) == ("BLOCKED", "WAITING")
    assert second["reason"] == (
        f"the task is recorded and waits for {first}, which holds this working tree"
    )


def test_a_task_waiting_for_its_dependency_says_so(plane: Any) -> None:
    first = work.start(plane, REQUEST, claim=False)["task"]["id"]

    second = work.start(plane, "Share a constant between src/app.py and src/other.py")

    assert second["task"]["dependencies"] == [first]
    assert (second["status"], second["state"]) == ("BLOCKED", "WAITING")
    assert second["readiness"]["waiting_for"] == [first]
    assert second["reason"] == "the task is recorded and waits for the work it depends on"


def test_linking_to_open_work_carries_the_preflight_and_claims_it(plane: Any) -> None:
    first = work.start(plane, REQUEST, claim=False)
    assert first["task"]["state"] == "READY"

    again = work.start(plane, REQUEST, agent="second-agent", capabilities=["code", "testing"])

    assert again["matched_by"] == "the same request was made before"
    assert again["preflight"]["mode"] == "FULL"
    assert again["approved_commands"] == []
    assert again["task"]["state"] == "CLAIMED"
    assert again["session"]
    agent = next(a for a in plane.store.list("agent") if a["name"] == "second-agent")
    assert agent["capabilities"] == ["code", "testing"]


def test_a_finished_task_is_never_linked_again(plane: Any) -> None:
    first = work.start(plane, REQUEST, claim=False)["task"]
    for state in ("COMPLETED", "CANCELLED"):
        current = plane.store.get(first["id"], "task")
        with plane.store.transaction():
            plane.store.put("task", {**current, "state": state}, expected=current["version"])

        again = work.start(plane, REQUEST, claim=False)

        assert again["task"]["id"] != first["id"]
        assert again["matched_by"] == "derived from this request"
        with plane.store.transaction():
            fresh = plane.store.get(again["task"]["id"], "task")
            plane.store.put("task", {**fresh, "state": "CANCELLED"}, expected=fresh["version"])
