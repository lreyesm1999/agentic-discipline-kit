"""What a repair run plans, answers and records, whole.

`test_repair` drives real repairs against real damage. These hand the planner a readiness
report directly and replace each repair with one that says it ran, so the choice of repairs,
their order, the answer and the audit record can each be pinned exactly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agentic_discipline import readiness, repair
from agentic_discipline.bootstrap import initialize_project
from agentic_discipline.common import AgenticError, run_git
from agentic_discipline.control.plane import Plane


def _check(name: str, status: str = "PASS", caused_by: str | None = None) -> dict[str, Any]:
    return {"name": name, "status": status, "caused_by": caused_by}


def _report(state: str = "READY", *checks: dict[str, Any]) -> dict[str, Any]:
    return {"execution_readiness": state, "checks": list(checks)}


def _names(chosen: list[tuple[str, repair.Repair]]) -> list[str]:
    return [name for name, _ in chosen]


# --- what gets planned ---------------------------------------------------------------------


def test_repairs_run_in_dependency_order_whatever_order_they_are_reported_in() -> None:
    report = _report(
        "PARTIAL",
        _check("knowledge", "STALE"),
        _check("control_plane", "MISSING"),
        _check("agent_adapter", "STALE"),
        _check("installation", "MISSING"),
    )

    assert _names(repair.plan(report)) == [
        "installation",
        "agent_adapter",
        "control_plane",
        "knowledge",
    ]


def test_one_repair_that_answers_several_checks_is_planned_once() -> None:
    report = _report(
        "PARTIAL",
        _check("quality_gates", "MISSING"),
        _check("disciplines", "STALE"),
    )

    chosen = repair.plan(report)

    assert chosen == [("disciplines", repair.PAYLOAD)]


def test_only_missing_or_stale_checks_with_no_other_cause_are_repaired() -> None:
    report = _report(
        "PARTIAL",
        _check("installation", "FAIL"),
        _check("agent_adapter", "OFF"),
        _check("control_plane", "PASS"),
        _check("knowledge", "MISSING", caused_by="control_plane"),
        _check("git_integration", "MISSING"),
    )

    assert repair.plan(report) == []


def test_each_repair_states_what_it_writes() -> None:
    assert repair.REPAIRS["agent_adapter"].report("done") == {
        "action": "recompile the agent surfaces",
        "writes": ["AGENTS.md", ".agentic/skills/"],
        "outcome": "done",
    }
    assert repair.REPAIRS["control_plane"].report("x")["writes"] == [
        str(Path(".agentic") / "control")
    ]
    assert repair.REPAIRS["knowledge"].report("x")["action"] == "reindex the project"
    assert repair.PAYLOAD.report("x")["writes"] == [".agentic/"]


# --- the answer ----------------------------------------------------------------------------


@pytest.fixture
def staged(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Readiness answers from a list, and the repairs report instead of acting."""

    seen: dict[str, Any] = {"reports": [], "deep": [], "ran": [], "records": []}

    def inspect(root: Path, *, deep: bool) -> dict[str, Any]:
        seen["deep"].append(deep)
        report: dict[str, Any] = seen["reports"].pop(0)
        return report

    def succeed(root: Path) -> str:
        seen["ran"].append(root)
        return "it ran"

    def fail(root: Path) -> str:
        raise AgenticError("it broke")

    monkeypatch.setattr(readiness, "inspect", inspect)
    monkeypatch.setattr(
        repair,
        "REPAIRS",
        {
            "agent_adapter": repair.Repair("works", ("a",), succeed),
            "control_plane": repair.Repair("breaks", ("b",), fail),
        },
    )
    monkeypatch.setattr(repair, "_record", lambda *args: seen["records"].append(args))
    return seen


def test_a_dry_run_answers_with_exactly_its_plan(staged: dict[str, Any], tmp_path: Path) -> None:
    before = _report("PARTIAL", _check("agent_adapter", "STALE"))
    staged["reports"] = [before]

    result = repair.apply(tmp_path / "." / "x", dry_run=True, deep=False)

    assert staged["deep"] == [False]
    assert staged["ran"] == []
    assert result == {
        "root": str((tmp_path / "x").resolve()),
        "dry_run": True,
        "before": "PARTIAL",
        "repaired": [],
        "planned": [
            {"action": "works", "writes": ["a"], "outcome": "would run", "check": "agent_adapter"}
        ],
        "failed": [],
        "readiness": before,
        "status": "PASS",
    }


def test_a_run_answers_with_what_ran_what_failed_and_what_is_left(
    staged: dict[str, Any], tmp_path: Path
) -> None:
    before = _report(
        "PARTIAL", _check("agent_adapter", "STALE"), _check("control_plane", "MISSING")
    )
    after = _report("PARTIAL", _check("control_plane", "MISSING"))
    staged["reports"] = [before, after]

    result = repair.apply(tmp_path)

    assert staged["deep"] == [True, True]
    assert staged["ran"] == [tmp_path.resolve()]
    assert result == {
        "root": str(tmp_path.resolve()),
        "dry_run": False,
        "before": "PARTIAL",
        "repaired": [
            {"action": "works", "writes": ["a"], "outcome": "it ran", "check": "agent_adapter"}
        ],
        "planned": [],
        "failed": [
            {
                "action": "breaks",
                "writes": ["b"],
                "outcome": "failed: it broke",
                "check": "control_plane",
            }
        ],
        "readiness": after,
        "status": "FAIL",
    }
    assert staged["records"] == [
        (tmp_path.resolve(), result["repaired"], result["failed"], before, after)
    ]


@pytest.mark.parametrize(
    ("after", "status"),
    [("READY", "PASS"), ("DEGRADED", "PASS"), ("PARTIAL", "FAIL"), ("BLOCKED", "FAIL")],
)
def test_a_run_passes_only_when_it_leaves_a_usable_project(
    staged: dict[str, Any], tmp_path: Path, after: str, status: str
) -> None:
    staged["reports"] = [_report("PARTIAL", _check("agent_adapter", "STALE")), _report(after)]

    assert repair.apply(tmp_path)["status"] == status


# --- the audit record ----------------------------------------------------------------------


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (root / "app.py").write_text("value = 1\n", encoding="utf-8")
    run_git(["init"], cwd=root)
    initialize_project(root)
    return root


def _repairs(root: Path) -> list[dict[str, Any]]:
    with Plane(root) as plane:
        return [e for e in plane.store.timeline() if e["action"] == "readiness.repair"]


def test_the_audit_record_names_both_states_and_each_action(project: Path) -> None:
    repair._record(
        project,
        [{"action": "reindex the project"}],
        [{"action": "recompile the agent surfaces"}],
        {"execution_readiness": "PARTIAL"},
        {"execution_readiness": "READY"},
    )

    (event,) = _repairs(project)
    assert event["actor"] == "local-owner"
    assert event["payload"] == {
        "from": "PARTIAL",
        "to": "READY",
        "repaired": ["reindex the project"],
        "failed": ["recompile the agent surfaces"],
    }


def test_a_run_that_did_nothing_records_nothing(project: Path) -> None:
    state = {"execution_readiness": "READY"}

    repair._record(project, [], [], state, state)
    assert _repairs(project) == []
    repair._record(project, [], [{"action": "x"}], state, state)
    assert len(_repairs(project)) == 1


def test_there_is_no_record_without_a_control_plane_to_hold_it(tmp_path: Path) -> None:
    state = {"execution_readiness": "READY"}

    repair._record(tmp_path, [{"action": "x"}], [], state, state)

    assert not (tmp_path / readiness.CONTROL_DIR).exists()
