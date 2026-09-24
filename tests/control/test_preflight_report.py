"""The preflight's answer, whole, for each readiness it can be handed.

The preflight adds no checks of its own: it folds the readiness report into eight
requirements, picks a mode and says what that mode cannot do. So each case here hands it a
readiness report directly and pins the answer entire, the refusal each mode produces, and
the text a person reads.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agentic_discipline import readiness, repair
from agentic_discipline.control import preflight
from agentic_discipline.control.contracts import ControlError

ORDER = ("FAIL", "MISSING", "STALE", "OFF", "PASS")
CHECKS = (
    "installation",
    "version",
    "control_plane",
    "project_adoption",
    "knowledge",
    "git_integration",
    "quality_gates",
    "disciplines",
    "agent_adapter",
    "task_orchestration",
)


def _check(name: str, status: str = "PASS", **fields: Any) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "detail": f"{name} is {status}",
        "repair": None,
        "advisory": False,
        "caused_by": None,
        **fields,
    }


def _report(state: str, reason: str, **overrides: dict[str, Any]) -> dict[str, Any]:
    return {
        "execution_readiness": state,
        "reason": reason,
        "checks": [overrides.get(name, _check(name)) for name in CHECKS],
    }


def _requirement(name: str, status: str = "PASS", **fields: Any) -> dict[str, Any]:
    return {
        "requirement": name,
        "status": status,
        "detail": fields.pop("detail", f"{fields.pop('check', name)} is {status}"),
        "repair": None,
        "advisory": False,
        "caused_by": None,
        **fields,
    }


FULL_REQUIREMENTS = [
    _requirement("installation"),
    _requirement("version"),
    _requirement("control_plane"),
    _requirement("adoption", check="project_adoption"),
    _requirement("knowledge"),
    _requirement("git", check="git_integration"),
    _requirement("quality_configuration", check="quality_gates"),
    _requirement("task_orchestration"),
]


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace readiness and repair with a report the test chooses, and record the calls."""

    seen: dict[str, Any] = {"report": _report("READY", "ready"), "inspect": [], "apply": []}

    def inspect(root: Path, *, deep: bool) -> dict[str, Any]:
        seen["inspect"].append((root, deep))
        return dict(seen["report"])

    def apply(root: Path, *, deep: bool) -> dict[str, Any]:
        seen["apply"].append((root, deep))
        return {
            "readiness": dict(seen["report"]),
            "repaired": [{"action": "adopt", "outcome": "adopted"}],
            "failed": [{"action": "index", "outcome": "no files"}],
        }

    monkeypatch.setattr(readiness, "inspect", inspect)
    monkeypatch.setattr(repair, "apply", apply)
    return seen


# --- the worst check answers for its requirement -------------------------------------------


@pytest.mark.parametrize(
    ("worse", "better"),
    [(ORDER[i], ORDER[j]) for i in range(len(ORDER)) for j in range(i + 1, len(ORDER))],
)
def test_the_worse_of_two_checks_answers_for_the_requirement(worse: str, better: str) -> None:
    # The better one comes first, so a tie in the ordering would wrongly pick it.
    checks = [_check("disciplines", better), _check("quality_gates", worse)]

    assert preflight._requirement("quality_configuration", checks)["status"] == worse


def test_a_requirement_says_which_other_requirement_explains_it() -> None:
    caused = _check("knowledge", "MISSING", caused_by="control_plane", repair="agentic repair")

    assert preflight._requirement("knowledge", [caused]) == {
        "requirement": "knowledge",
        "status": "MISSING",
        "detail": "knowledge is MISSING",
        "repair": "agentic repair",
        "advisory": False,
        "caused_by": "control_plane",
    }
    git = _check("task_orchestration", "MISSING", caused_by="git_integration")
    assert preflight._requirement("task_orchestration", [git])["caused_by"] == "git"
    unknown = _check("task_orchestration", "MISSING", caused_by="something_else")
    assert preflight._requirement("task_orchestration", [unknown])["caused_by"] is None


# --- the mode and the whole answer ---------------------------------------------------------


def test_a_ready_project_is_full_and_the_answer_is_exactly_this(
    calls: dict[str, Any], tmp_path: Path
) -> None:
    result = preflight.run(tmp_path / "." / "project", repair_first=False, deep=False)

    root = (tmp_path / "project").resolve()
    assert calls["inspect"] == [(root, False)]
    assert calls["apply"] == []
    assert result == {
        "root": str(root),
        "mode": "FULL",
        "reason": "every requirement is met; the full workflow is available",
        "requirements": FULL_REQUIREMENTS,
        "repaired": [],
        "failed": [],
        "unavailable": [],
        "safe_to_proceed": True,
        "readiness": calls["report"],
        "status": "PASS",
    }


def test_repairing_first_reports_what_was_repaired_and_what_was_not(
    calls: dict[str, Any], tmp_path: Path
) -> None:
    result = preflight.run(tmp_path, deep=True)

    assert calls["apply"] == [(tmp_path.resolve(), True)]
    assert calls["inspect"] == []
    assert result["repaired"] == [{"action": "adopt", "outcome": "adopted"}]
    assert result["failed"] == [{"action": "index", "outcome": "no files"}]
    preflight.run(tmp_path, deep=False)
    assert calls["apply"][-1] == (tmp_path.resolve(), False)
    preflight.run(tmp_path, repair_first=False)
    assert calls["inspect"] == [(tmp_path.resolve(), True)]


def test_a_degraded_project_names_the_orchestration_it_lacks(
    calls: dict[str, Any], tmp_path: Path
) -> None:
    calls["report"] = _report("DEGRADED", "rules only")

    result = preflight.run(tmp_path, repair_first=False)

    assert (result["mode"], result["reason"], result["status"]) == (
        "DEGRADED",
        "rules only",
        "FAIL",
    )
    assert result["safe_to_proceed"] is True
    assert result["unavailable"] == [
        "task contracts and their readiness",
        "leases, so two agents cannot claim the same work",
        "checkpoints and resumable state",
        "recorded evidence and proof obligations",
        "the completion invariant",
    ]


def test_a_project_without_git_loses_what_needs_a_commit(
    calls: dict[str, Any], tmp_path: Path
) -> None:
    calls["report"] = _report(
        "READY", "ready", git_integration=_check("git_integration", "MISSING")
    )

    result = preflight.run(tmp_path, repair_first=False)

    assert result["mode"] == "FULL"
    assert result["unavailable"] == [
        "workspace isolation",
        "change integrity checks",
        "rollback to a checkpoint",
    ]


def test_blocked_is_the_reason_and_lists_nothing_as_unavailable(
    calls: dict[str, Any], tmp_path: Path
) -> None:
    calls["report"] = _report(
        "PARTIAL", "history altered", git_integration=_check("git_integration", "FAIL")
    )

    result = preflight.run(tmp_path, repair_first=False)

    assert (result["mode"], result["reason"]) == ("BLOCKED", "history altered")
    assert (result["unavailable"], result["safe_to_proceed"], result["status"]) == (
        [],
        False,
        "FAIL",
    )


def test_the_preflight_of_a_plane_is_the_preflight_of_its_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: list[tuple[Any, ...]] = []
    monkeypatch.setattr(
        preflight,
        "run",
        lambda root, *, repair_first, deep: seen.append((root, repair_first, deep)) or {},
    )

    class Opened:
        root = tmp_path

    preflight.for_plane(Opened())
    preflight.for_plane(Opened(), repair_first=False, deep=False)

    assert seen == [(tmp_path, True, True), (tmp_path, False, False)]


# --- what each mode refuses ----------------------------------------------------------------


def _refusal(result: dict[str, Any], **needs: bool) -> tuple[str, str]:
    with pytest.raises(ControlError) as refused:
        preflight.requires(result, **needs)
    return refused.value.code, str(refused.value)


def _result(mode: str, git: str = "PASS") -> dict[str, Any]:
    return {
        "mode": mode,
        "reason": f"because {mode}",
        "requirements": [_requirement("git", git, detail="not a repository")],
    }


def test_each_mode_refuses_exactly_what_it_cannot_support() -> None:
    assert _refusal(_result("BLOCKED"), orchestration=False) == (
        "NOT_READY",
        "Execution is blocked: because BLOCKED",
    )
    assert _refusal(_result("DEGRADED")) == (
        "DEGRADED_MODE",
        "This needs the full workflow, which is unavailable: because DEGRADED",
    )
    assert _refusal(_result("FULL", "MISSING"), git=True) == (
        "NOT_READY",
        "This needs a git working tree: not a repository",
    )
    preflight.requires(_result("DEGRADED"), orchestration=False)
    preflight.requires(_result("FULL", "MISSING"))
    preflight.requires(_result("FULL"), git=True)


# --- what a person reads -------------------------------------------------------------------


def test_the_rendered_report_is_exactly_this() -> None:
    result = {
        "mode": "DEGRADED",
        "reason": "rules only",
        "requirements": [
            _requirement("git", "MISSING", detail="no repository", repair="git init"),
            _requirement("control_plane", "MISSING", detail="no plane"),
            _requirement("knowledge", "MISSING", caused_by="control_plane"),
            _requirement("version", "STALE", advisory=True),
            _requirement("adoption", "OFF"),
            _requirement("installation"),
            # Caused by a requirement that passes, so nothing above has explained it.
            _requirement(
                "task_orchestration", "MISSING", detail="no tasks", caused_by="installation"
            ),
        ],
        "repaired": [{"action": "adopt", "outcome": "adopted"}],
        "failed": [{"action": "index", "outcome": "no files"}],
        "unavailable": ["the completion invariant"],
        "safe_to_proceed": True,
    }

    assert preflight.render(result) == "\n".join(
        [
            "Execution mode: DEGRADED",
            "",
            "  git                 MISSING",
            "  control_plane       MISSING",
            "  knowledge           MISSING",
            "  version             STALE",
            "  adoption            OFF",
            "  installation        PASS",
            "  task_orchestration  MISSING",
            "",
            "Reason: rules only",
            "",
            "Repaired automatically:",
            "  - adopt: adopted",
            "",
            "Could not repair:",
            "  ! index: no files",
            "",
            "Unavailable:",
            "  - the completion invariant",
            "",
            "Outstanding:",
            "  - git (MISSING): no repository",
            "    Repair: git init",
            "  - control_plane (MISSING): no plane",
            "  - task_orchestration (MISSING): no tasks",
            "",
            "Proceeding is safe for the work this mode supports.",
        ]
    )


def test_a_clean_report_has_no_empty_sections_and_a_blocked_one_says_stop() -> None:
    result = {
        "mode": "BLOCKED",
        "reason": "history altered",
        "requirements": [_requirement("git")],
        "repaired": [],
        "failed": [],
        "unavailable": [],
        "safe_to_proceed": False,
    }

    assert preflight.render(result) == "\n".join(
        [
            "Execution mode: BLOCKED",
            "",
            "  git  PASS",
            "",
            "Reason: history altered",
            "",
            "Do not proceed: the workflow this project claims is not available.",
        ]
    )
