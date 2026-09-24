"""The status table a person reads, pinned line for line.

The table is aligned on its widest label, which is sometimes one of the checks and sometimes
one of the three summaries, so both cases are here, with and without anything outstanding.
"""

from __future__ import annotations

from typing import Any

from agentic_discipline import readiness


def _check(label: str, status: str = "PASS", repair: str | None = None) -> dict[str, Any]:
    return {"label": label, "status": status, "detail": f"{label} detail", "repair": repair}


def _report(*checks: dict[str, Any]) -> dict[str, Any]:
    return {
        "checks": list(checks),
        "installation": "HEALTHY",
        "project": "DRIFTED",
        "execution_readiness": "PARTIAL",
        "reason": "something is missing",
    }


def test_short_labels_are_aligned_on_the_widest_summary() -> None:
    report = _report(
        _check("Version"),
        _check("Knowledge", "STALE", repair="agentic reconcile"),
        _check("Git", "MISSING"),
    )

    assert readiness.render(report) == "\n".join(
        [
            "Agentic Discipline status",
            "",
            "Version              PASS",
            "Knowledge            STALE",
            "Git                  MISSING",
            "",
            "Installation health  HEALTHY",
            "Project health       DRIFTED",
            "Execution readiness  PARTIAL",
            "",
            "Reason: something is missing",
            "",
            "Outstanding:",
            "- Knowledge (STALE): Knowledge detail\n  Repair: agentic reconcile",
            "- Git (MISSING): Git detail",
        ]
    )


def test_a_long_label_widens_the_whole_table_and_nothing_outstanding_adds_nothing() -> None:
    report = _report(_check("A label longer than any summary"), _check("Git"))

    assert readiness.render(report) == "\n".join(
        [
            "Agentic Discipline status",
            "",
            "A label longer than any summary  PASS",
            "Git                              PASS",
            "",
            "Installation health              HEALTHY",
            "Project health                   DRIFTED",
            "Execution readiness              PARTIAL",
            "",
            "Reason: something is missing",
        ]
    )
