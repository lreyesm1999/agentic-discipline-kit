"""The plain-text reading of `agentic assurance`, line by line.

This is what a person reads when they ask why a task cannot complete, so a heading that
changes case, a line that disappears or a section that overwrites the one before it is a
real regression. Every branch is pinned with fixed input and the whole output.
"""

from __future__ import annotations

from typing import Any

from agentic_discipline.control.cli import render_assurance


def _outstanding(**changes: Any) -> dict[str, Any]:
    return {
        "status": "STALE",
        "obligation_id": "PO-1",
        "claim": "Totals are correct",
        "reason": "the evidence for this claim no longer matches current inputs",
        "current_evidence": ["EVID-1"],
        "stale_evidence": ["EVID-2"],
        **changes,
    }


def test_explaining_a_task_names_every_open_claim_and_what_to_do_next() -> None:
    data = {
        "headline": "TASK-1 cannot complete: 2 obligations are unresolved.",
        "required": 3,
        "counts": {"VERIFIED": 1, "STALE": 1, "UNKNOWN": 1},
        "outstanding": [
            _outstanding(),
            _outstanding(
                status="UNKNOWN",
                obligation_id="PO-2",
                claim="Refunds are refused twice",
                reason="a required verifier returned no verdict",
                current_evidence=[],
                stale_evidence=[],
            ),
        ],
        "required_next_actions": ["rerun unit", "resolve PO-2 by hand"],
    }

    assert render_assurance("explain", data).splitlines() == [
        "TASK-1 cannot complete: 2 obligations are unresolved.",
        "3 mandatory proof obligations.",
        "  STALE            1",
        "  UNKNOWN          1",
        "  VERIFIED         1",
        "",
        "STALE:",
        "  PO-1",
        "  Totals are correct",
        "  Reason: the evidence for this claim no longer matches current inputs",
        "  Evidence: EVID-1",
        "  Evidence: EVID-2",
        "",
        "UNKNOWN:",
        "  PO-2",
        "  Refunds are refused twice",
        "  Reason: a required verifier returned no verdict",
        "",
        "Required next actions:",
        "  1. rerun unit",
        "  2. resolve PO-2 by hand",
    ]


def test_a_task_with_nothing_left_to_do_has_no_next_actions_section() -> None:
    data = {
        "headline": "TASK-1 can complete.",
        "required": 1,
        "counts": {"VERIFIED": 1},
        "outstanding": [],
        "required_next_actions": [],
    }

    assert render_assurance("explain", data).splitlines() == [
        "TASK-1 can complete.",
        "1 mandatory proof obligations.",
        "  VERIFIED         1",
    ]


def _obligation(**changes: Any) -> dict[str, Any]:
    return {
        "obligation": {"id": "PO-1"},
        "claim": "Totals are correct",
        "required_because": "acceptance criterion 0 of TASK-1",
        "affected_paths": ["src/app.py", "src/totals.py"],
        "evidence": [
            {
                "id": "EVID-1",
                "result": "PASS",
                "currency": "current",
                "kind": "unit",
                "evidence_class": "DETERMINISTIC",
            }
        ],
        "status": "VERIFIED",
        "reason": "every required verifier has current passing evidence",
        "human_request": None,
        **changes,
    }


def test_explaining_one_obligation_shows_its_claim_origin_scope_evidence_and_state() -> None:
    assert render_assurance("explain", _obligation()).splitlines() == [
        "PO-1",
        "Claim:",
        "  Totals are correct",
        "Origin:",
        "  acceptance criterion 0 of TASK-1",
        "Affected by:",
        "  src/app.py",
        "  src/totals.py",
        "Evidence:",
        "  EVID-1 PASS current (unit, DETERMINISTIC)",
        "Current state:",
        "  VERIFIED - every required verifier has current passing evidence",
    ]


def test_an_obligation_with_no_paths_evidence_or_verdict_says_so_plainly() -> None:
    data = _obligation(
        affected_paths=[],
        evidence=[],
        status="HUMAN_REQUIRED",
        reason="no automated verifier can settle this claim",
        human_request={"resolve_with": "agentic assurance resolve PO-1 --decision PASS"},
    )

    assert render_assurance("explain", data).splitlines() == [
        "PO-1",
        "Claim:",
        "  Totals are correct",
        "Origin:",
        "  acceptance criterion 0 of TASK-1",
        "Affected by:",
        "  (declared task scope)",
        "Evidence:",
        "  none recorded",
        "Current state:",
        "  HUMAN_REQUIRED - no automated verifier can settle this claim",
        "Human resolution:",
        "  agentic assurance resolve PO-1 --decision PASS",
    ]


def _report(**changes: Any) -> dict[str, Any]:
    return {
        "task_id": "TASK-1",
        "required": 2,
        "counts": {"VERIFIED": 1, "FAILED": 1},
        "proof_debt": 1,
        "decision": {"decision": "REPAIR"},
        "outstanding": [
            {"obligation_id": "PO-2", "status": "FAILED", "claim": "Refunds are refused twice"}
        ],
        **changes,
    }


def test_status_shows_counts_debt_the_decision_and_the_open_claims() -> None:
    assert render_assurance("status", {"tasks": [_report()]}).splitlines() == [
        "TASK-1 ASSURANCE",
        "  Required obligations 2",
        "  FAILED                 1",
        "  VERIFIED               1",
        "  Proof debt           1",
        "  Decision             REPAIR",
        "  - PO-2 FAILED: Refunds are refused twice",
    ]


def test_debt_has_no_decision_line() -> None:
    report = _report(counts={"FAILED": 1})
    report.pop("decision")

    assert render_assurance("debt", {"tasks": [report]}).splitlines() == [
        "TASK-1 ASSURANCE",
        "  Required obligations 2",
        "  FAILED                 1",
        "  Proof debt           1",
        "  - PO-2 FAILED: Refunds are refused twice",
    ]


def test_a_project_with_no_plan_says_so_rather_than_printing_nothing() -> None:
    assert render_assurance("status", {"tasks": []}) == "No assurance plan has been compiled yet"
