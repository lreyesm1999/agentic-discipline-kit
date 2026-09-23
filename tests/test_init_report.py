"""Human `init` report, line by line.

`agentic-discipline init` prints the only summary most users read before trusting the
generated configuration. The existing test checked one line, so the report could
drop a relaxed gate warning, miscount files or hide the dry-run banner unnoticed.
Each case compares the whole printed report.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agentic_discipline.cli import _counts, _render_init


def _result(root: Path, **changes: object) -> dict[str, object]:
    return {
        "target": str(root),
        "dry_run": False,
        "detections": [
            {"label": "Python", "root": "."},
            {"label": "TypeScript / JavaScript", "root": "web"},
        ],
        "adapters": ["claude", "generic"],
        "adapter_labels": ["Claude Code", "Generic AGENTS.md"],
        "disciplines": ["a", "b", "c"],
        "gates": 5,
        "relaxed_gates": [
            {"name": "typecheck", "note": "disabled by init: mypy is not installed"},
            {"name": "e2e", "note": "no browser available"},
        ],
        "baseline_gate": "syntax",
        "control_mode": "managed",
        "control": {"status": "ADOPTED", "detail": "the repository was adopted and indexed"},
        "readiness": {
            "execution_readiness": "READY",
            "reason": "every check passes; the full workflow is available",
            "checks": [],
        },
        "actions": [
            f"WRITE {root}/AGENTS.md",
            f"WRITE {root}/agentic.config.json",
            f"SKIP {root}/.gitignore (already configured)",
            f"UPDATE {root}/.agentic/config.json",
            "READY",
        ],
        **changes,
    }


def test_full_report_lists_every_surface_gate_caveat_and_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _render_init(_result(tmp_path))
    assert capsys.readouterr().out.splitlines() == [
        f"Agentic Discipline -> {tmp_path.resolve()}",
        "",
        "  Detected stack   Python (.), TypeScript / JavaScript (web)",
        "  Disciplines      3 installed",
        "  Agent surfaces   2",
        "                   - Claude Code",
        "                   - Generic AGENTS.md",
        "  Quality gates    5 generated, 2 relaxed",
        "                   ! typecheck: mypy is not installed",
        "                   ! e2e: no browser available",
        "                   + syntax: added so the config still checks something",
        "  Files            1 ready, 1 skip, 1 update, 2 write",
        "  Control plane    the repository was adopted and indexed",
        "",
        "Visible in your repository root: AGENTS.md, agentic.config.json",
        "Everything else lives in .agentic/",
        "",
        "Review the relaxed gates in agentic.config.json before making CI blocking.",
        "Status: READY FOR AGENTIC EXECUTION",
        "",
        "Next:  ask for the work you want done.",
    ]


def test_a_report_that_is_not_ready_names_every_gap_and_its_repair(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _render_init(
        _result(
            tmp_path,
            relaxed_gates=[],
            baseline_gate=None,
            control={"status": "BLOCKED", "detail": "Control directory already exists"},
            readiness={
                "execution_readiness": "BROKEN",
                "reason": "Control plane: .agentic/control exists without a state database",
                "checks": [
                    {
                        "label": "Control plane",
                        "status": "FAIL",
                        "detail": "exists without a state database",
                        "repair": None,
                        "advisory": False,
                    },
                    {
                        "label": "Knowledge",
                        "status": "MISSING",
                        "detail": "no knowledge store",
                        "repair": "agentic reconcile",
                        "advisory": False,
                    },
                    {
                        "label": "Git integration",
                        "status": "PASS",
                        "detail": "working tree",
                        "repair": None,
                        "advisory": False,
                    },
                ],
            },
        )
    )
    assert capsys.readouterr().out.splitlines()[-9:] == [
        "",
        "Status: BROKEN",
        "",
        "Reason: Control plane: .agentic/control exists without a state database",
        "  - Control plane (FAIL): exists without a state database",
        "  - Knowledge (MISSING): no knowledge store",
        "    Repair: agentic reconcile",
        "",
        "Next:  agentic-discipline doctor --check-tools",
    ]


def test_dry_run_report_without_caveats(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _render_init(
        _result(
            tmp_path,
            dry_run=True,
            adapters=[],
            adapter_labels=[],
            relaxed_gates=[],
            baseline_gate=None,
            actions=[f"WRITE {tmp_path}/AGENTS.md"],
            control={"status": "PENDING", "detail": "would adopt the repository and index it"},
            readiness=None,
        )
    )
    assert capsys.readouterr().out.splitlines() == [
        f"Agentic Discipline -> {tmp_path.resolve()}",
        "DRY RUN - nothing was written.",
        "  Detected stack   Python (.), TypeScript / JavaScript (web)",
        "  Disciplines      3 installed",
        "  Agent surfaces   0",
        "  Quality gates    5 generated, 0 relaxed",
        "  Files            1 write",
        "  Control plane    would adopt the repository and index it",
        "",
        "Visible in your repository root: AGENTS.md, agentic.config.json",
        "Everything else lives in .agentic/",
        "",
        "Next:  agentic-discipline init        (this run wrote nothing)",
    ]


def test_a_missing_dry_run_flag_means_files_were_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = _result(tmp_path)
    del result["dry_run"]
    del result["baseline_gate"]
    _render_init(result)
    lines = capsys.readouterr().out.splitlines()
    assert lines[1] == ""
    assert not any("added so the config still checks something" in line for line in lines)


def test_action_counts_group_by_leading_verb() -> None:
    assert _counts(["WRITE a", "WRITE b c", "SKIP d (already exists)", "READY"]) == {
        "WRITE": 2,
        "SKIP": 1,
        "READY": 1,
    }
    assert _counts([]) == {}
