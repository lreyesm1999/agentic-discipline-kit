"""The assurance service's guards: identifiers of the wrong kind, forged links, one task of many.

Every entry point reads its record with the kind it expects, so an identifier of another kind
is refused instead of being treated as the thing it is not. The links an obligation carries -
its task, its requirements, its waiver - are read the same way, and are tested by forging
the obligation, since nothing the service writes can produce a wrong link on its own. That is
defence in depth, kept and tested rather than trusted.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest
from assurance_support import claimed, contract, planned, sources

from agentic_discipline.control.assurance import service
from agentic_discipline.control.contracts import ControlError
from agentic_discipline.control.plane import Plane, adopt


@pytest.fixture
def plane(tmp_path: Path) -> Any:
    sources(tmp_path, {"src/report.py": "value = 1\n", "src/other.py": "other = 2\n"})
    adopt(tmp_path)
    with Plane(tmp_path) as opened:
        yield opened


def _task(plane: Any, **overrides: Any) -> tuple[str, str]:
    task, session = claimed(plane, contract(**overrides))
    service.compile_plan(plane, task, phase="INITIAL")
    return task, session


def _obligation(plane: Any, task: str) -> dict[str, Any]:
    return dict(service.obligations_for(plane, task)[0])


def _forge(plane: Any, obligation: dict[str, Any], **changes: Any) -> None:
    with plane.store.transaction():
        plane.store.put("obligation", {**obligation, **changes}, expected=obligation["version"])


def _refused(identifier: str) -> Any:
    return pytest.raises(ControlError, match=f"^Record not found: {identifier}$")


# --- an identifier of the wrong kind ---------------------------------------------------------


def test_every_entry_point_refuses_an_identifier_of_another_kind(plane: Any) -> None:
    task, session = _task(plane)
    obligation = _obligation(plane, task)["id"]
    agent = plane.store.list("agent")[0]["id"]

    with _refused(obligation):
        service.compile_plan(plane, obligation, phase="INITIAL")
    with _refused(agent):
        service.status(plane, agent)
    with _refused(agent):
        service.debt_report(plane, agent)
    with _refused(agent):
        service.explain(plane, agent)
    with _refused(task):
        service.explain_obligation(plane, task)
    with _refused(task):
        service.waive(plane, task, "accepted", "owner")
    with _refused(task):
        service.resolve_human(plane, task, "looks right")


# --- a link that points at the wrong kind ----------------------------------------------------


def test_an_obligation_whose_task_is_not_a_task_is_refused_everywhere_it_is_read(
    plane: Any,
) -> None:
    task, _ = _task(plane)
    obligation = _obligation(plane, task)
    agent = plane.store.list("agent")[0]["id"]
    _forge(plane, obligation, task_id=agent)

    with _refused(agent):
        service.explain_obligation(plane, obligation["id"])
    with _refused(agent):
        service.waive(plane, obligation["id"], "accepted", "owner")
    with _refused(agent):
        service.resolve_human(plane, obligation["id"], "looks right")


def test_a_requirement_link_that_is_not_a_requirement_is_refused(plane: Any) -> None:
    task, _ = _task(plane)
    obligation = _obligation(plane, task)
    _forge(plane, obligation, origin={**obligation["origin"], "requirement_ids": [task]})

    with _refused(task):
        service.explain_obligation(plane, obligation["id"])


def test_a_waiver_link_that_is_not_a_waiver_is_refused(plane: Any) -> None:
    task, _ = _task(plane)
    obligation = _obligation(plane, task)
    _forge(plane, obligation, status="WAIVED", waiver_id=task)

    with _refused(task):
        service.explain_obligation(plane, obligation["id"])


# --- one task among several ------------------------------------------------------------------


def test_status_and_debt_for_one_task_leave_the_others_out(plane: Any) -> None:
    first, _ = _task(plane)
    # Planned rather than claimed: one working tree holds one claim.
    second = planned(plane, contract(scope=["src/other.py"], objective="Keep other at two"))
    service.compile_plan(plane, second, phase="INITIAL")

    assert {report["task_id"] for report in service.status(plane)["tasks"]} == {first, second}
    assert [report["task_id"] for report in service.status(plane, first)["tasks"]] == [first]
    assert [report["task_id"] for report in service.debt_report(plane, second)["tasks"]] == [second]


# --- the engine switched off -----------------------------------------------------------------


def test_a_project_on_the_2_0_schema_is_told_how_to_turn_the_engine_on(tmp_path: Path) -> None:
    sources(tmp_path, {"src/report.py": "value = 1\n"})
    adopt(tmp_path)
    with sqlite3.connect(tmp_path / ".agentic" / "control" / "state.db") as db:
        db.execute("UPDATE meta SET value='1' WHERE key='schema_version'")

    with Plane(tmp_path) as plane, pytest.raises(ControlError) as refused:
        service.status(plane)

    assert (refused.value.code, str(refused.value)) == (
        "ASSURANCE_DISABLED",
        "Run 'agentic assurance migrate' to enable the assurance engine for this project",
    )


# --- a human verdict is bound to what it judged ----------------------------------------------


def test_a_human_verdict_survives_an_edit_to_a_file_it_did_not_judge(plane: Any) -> None:
    """The verdict binds to its own obligation's inputs. Binding it to the whole task instead
    would make an unrelated edit read as a change to what the person looked at."""

    task, _ = _task(plane, scope=["src"])
    obligation = _obligation(plane, task)
    _forge(
        plane,
        obligation,
        affected_paths=["src/report.py"],
        # What the planner records for a claim no automated verifier can settle.
        required_verifiers=[f"human:{obligation['id']}"],
        plan={**obligation["plan"], "human_required": True},
    )
    service.resolve_human(plane, obligation["id"], "the report reads correctly")
    assert service.explain_obligation(plane, obligation["id"])["status"] == "VERIFIED"

    (Path(plane.root) / "src" / "other.py").write_text("other = 3\n", encoding="utf-8")

    assert service.explain_obligation(plane, obligation["id"])["status"] == "VERIFIED"
    (Path(plane.root) / "src" / "report.py").write_text("value = 2\n", encoding="utf-8")
    assert service.explain_obligation(plane, obligation["id"])["status"] == "STALE"
