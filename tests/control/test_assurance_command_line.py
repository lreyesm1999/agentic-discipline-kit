"""Every `agentic assurance` action, run through the command line in this process.

The command line is a thin layer over the versioned API, and a thin layer is easy to break
without noticing: the wrong operation name, a missing argument, an owner-only action sent
without the owner's authority, a refusal whose message changed. Each action here is run
through `main()` and compared with what the service itself answers.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from assurance_support import claimed, contract, planned, sources

from agentic_discipline.control.assurance import service
from agentic_discipline.control.cli import main
from agentic_discipline.control.plane import Plane, adopt


@pytest.fixture
def plane(tmp_path: Path) -> Any:
    sources(tmp_path, {"src/report.py": "value = 1\n"})
    adopt(tmp_path)
    with Plane(tmp_path) as opened:
        yield opened


def _run(plane: Any, *arguments: str) -> tuple[int, dict[str, Any] | str]:
    argv = ["agentic", "--root", str(plane.root), "assurance", *arguments]
    with mock.patch.object(sys, "argv", argv), mock.patch("sys.stdout") as stdout:
        try:
            main()
            code = 0
        except SystemExit as exit_:
            code = int(exit_.code or 0)
    written = "".join(call.args[0] for call in stdout.write.call_args_list)
    try:
        return code, json.loads(written)
    except ValueError:
        return code, written


def _task(plane: Any) -> tuple[str, str]:
    task, session = claimed(plane, contract())
    service.compile_plan(plane, task, phase="INITIAL")
    return task, session


def test_plan_reads_the_stored_plan_and_compile_writes_one(plane: Any) -> None:
    task, _ = claimed(plane, contract())

    code, answer = _run(plane, "plan", task, "--compile", "--json")
    assert code == 0
    compiled = answer["data"]  # type: ignore[index]
    assert compiled["task_id"] == task

    code, answer = _run(plane, "plan", task, "--json")
    assert code == 0
    assert answer["data"] == service.plan_view(plane, task)  # type: ignore[index]


def test_status_and_debt_answer_for_one_task_or_for_all(plane: Any) -> None:
    task, _ = _task(plane)
    # A second task, so "this task" and "every task" are different answers.
    other = planned(plane, contract(scope=["src/other.py"], objective="Keep other at two"))
    service.compile_plan(plane, other, phase="INITIAL")

    for action, expected in (
        ("status", service.status(plane, task)),
        ("debt", service.debt_report(plane, task)),
    ):
        code, answer = _run(plane, action, task, "--json")
        assert (code, answer["data"]) == (0, expected)  # type: ignore[index]
    code, answer = _run(plane, "status", "--json")
    assert answer["data"] == service.status(plane)  # type: ignore[index]
    assert len(answer["data"]["tasks"]) == 2  # type: ignore[index]


def test_status_and_debt_print_the_plain_report(plane: Any) -> None:
    task, _ = _task(plane)

    code, text = _run(plane, "status", task)
    assert code == 0
    assert str(text).startswith(f"{task} ASSURANCE")
    assert "  Decision             " in str(text)

    code, text = _run(plane, "debt", task)
    assert str(text).startswith(f"{task} ASSURANCE")
    assert "Decision" not in str(text)


def test_explain_answers_for_a_task_and_for_one_obligation(plane: Any) -> None:
    task, _ = _task(plane)
    obligation = service.obligations_for(plane, task)[0]["id"]

    code, answer = _run(plane, "explain", task, "--json")
    assert (code, answer["data"]) == (0, service.explain(plane, task))  # type: ignore[index]
    code, answer = _run(plane, "explain", obligation, "--json")
    assert answer["data"] == service.explain(plane, obligation)  # type: ignore[index]

    code, text = _run(plane, "explain", obligation)
    assert str(text).startswith(f"{obligation}\nClaim:\n")


def test_registry_and_integrity_are_read_without_arguments(plane: Any) -> None:
    code, answer = _run(plane, "registry", "--json")
    assert (code, answer["data"]) == (0, service.registry(plane))  # type: ignore[index]
    code, answer = _run(plane, "integrity", "--json")
    assert answer["data"] == service.integrity(plane)  # type: ignore[index]


def test_a_waiver_needs_a_reason_and_an_authority(plane: Any) -> None:
    task, _ = _task(plane)
    obligation = service.obligations_for(plane, task)[0]["id"]

    for missing in (["--authorization", "owner"], ["--reason", "accepted"]):
        code, answer = _run(plane, "waive", obligation, *missing)
        assert code == 2
        assert answer == {  # type: ignore[comparison-overlap]
            "api_version": "2",
            "status": "ERROR",
            "code": "DECISION_REQUIRED",
            "message": "A waiver needs --reason and --authorization",
        }

    code, answer = _run(
        plane,
        "waive",
        obligation,
        "--reason",
        "accepted risk",
        "--authorization",
        "owner",
        "--json",
    )
    assert code == 0
    assert service.obligations_for(plane, task)[0]["status"] == "WAIVED"


def test_a_human_verdict_needs_its_decision(plane: Any) -> None:
    task, _ = _task(plane)
    obligation = service.obligations_for(plane, task)[0]["id"]

    code, answer = _run(plane, "resolve", obligation)
    assert (code, answer["code"], answer["message"]) == (  # type: ignore[index]
        2,
        "DECISION_REQUIRED",
        "Record --decision",
    )


def test_migration_and_rollback_are_owner_actions_with_their_reason(plane: Any) -> None:
    code, answer = _run(plane, "migrate", "--dry-run", "--json")
    assert code == 0
    assert answer["data"]["dry_run"] is True  # type: ignore[index]

    code, answer = _run(plane, "rollback", "ASSU-0")
    assert (code, answer["code"], answer["message"]) == (  # type: ignore[index]
        2,
        "REASON_REQUIRED",
        "Rollback requires --reason",
    )


def test_verification_runs_the_task_s_verifiers_for_its_worker(plane: Any, tmp_path: Path) -> None:
    task, session = _task(plane)
    session_file = tmp_path.parent / f"{tmp_path.name}-session.json"
    session_file.write_text(json.dumps({"session": session}), encoding="utf-8")

    code, answer = _run(plane, "verify", task, "--session-file", str(session_file), "--json")

    assert code == 0
    assert answer["data"]["status"] == "PASS"  # type: ignore[index]


def test_a_rollback_with_its_reason_returns_the_project_to_where_it_was(plane: Any) -> None:
    from agentic_discipline.control.assurance import migration

    applied = migration.migrate(plane)

    code, answer = _run(
        plane, "rollback", applied["migration_id"], "--reason", "trying it later", "--json"
    )

    assert code == 0
    data = answer["data"]  # type: ignore[index]
    # Back to the schema the migration recorded it came from.
    assert (data["rolled_back"], data["schema_version"]) == (True, applied["from_schema"])
    assert data["migration"]["rollback_reason"] == "trying it later"
