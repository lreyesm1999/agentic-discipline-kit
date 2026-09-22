"""What every real execution starts with: is this project able to do the work, or not.

The answer is one of three modes, and none of them is silence. FULL means the whole workflow
is available. DEGRADED names what is unavailable, why, and what proceeding would and would not
give; it is never assumed, only reported. BLOCKED stops the work with the precise reason.

Nothing here decides what the work is. It decides whether the machinery the work depends on
exists, repairs what can be repaired without a decision, and says what is left.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import readiness, repair

MODES = ("FULL", "DEGRADED", "BLOCKED")

# The eight things an execution stands on, in the order they are reported. Each one names the
# readiness checks that answer it, so one report cannot drift from the other.
REQUIREMENTS = (
    ("installation", ("installation",)),
    ("version", ("version",)),
    ("control_plane", ("control_plane",)),
    ("adoption", ("project_adoption",)),
    ("knowledge", ("knowledge",)),
    ("git", ("git_integration",)),
    ("quality_configuration", ("quality_gates", "disciplines", "agent_adapter")),
    ("task_orchestration", ("task_orchestration",)),
)

# What a project without a control plane cannot do. Naming them is the difference between
# "continuing with Agentic Discipline principles" and saying what is actually missing.
ORCHESTRATION = (
    "task contracts and their readiness",
    "leases, so two agents cannot claim the same work",
    "checkpoints and resumable state",
    "recorded evidence and proof obligations",
    "the completion invariant",
)

# Operations that need git whatever else is true: a change nobody can bind to a commit cannot
# be verified, integrated, or rolled back to a known point.
NEEDS_GIT = ("workspace isolation", "change integrity checks", "rollback to a checkpoint")


# Which requirement a readiness check belongs to, so a check that is only failing because of
# another one points at the requirement that explains it rather than at a check name.
ANSWERED_BY = {check: name for name, sources in REQUIREMENTS for check in sources}


def _requirement(name: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
    """The worst of the readiness checks that answer this requirement, with its reason."""

    ordering = {"FAIL": 0, "MISSING": 1, "STALE": 2, "OFF": 3, "PASS": 4}
    worst = min(checks, key=lambda check: ordering[str(check["status"])])
    cause = worst["caused_by"]
    return {
        "requirement": name,
        "status": worst["status"],
        "detail": worst["detail"],
        "repair": worst["repair"],
        "advisory": worst["advisory"],
        "caused_by": ANSWERED_BY.get(str(cause)) if cause else None,
    }


def _requirements(report: dict[str, Any]) -> list[dict[str, Any]]:
    by_name = {str(check["name"]): check for check in report["checks"]}
    return [
        _requirement(name, [by_name[check] for check in sources if check in by_name])
        for name, sources in REQUIREMENTS
    ]


def run(root: Path, *, repair_first: bool = True, deep: bool = True) -> dict[str, Any]:
    """Check, repair what is safe, and report the mode the work may proceed in."""

    root = Path(root).resolve()
    repaired: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    if repair_first:
        attempt = repair.apply(root, deep=deep)
        report = attempt["readiness"]
        repaired, failed = attempt["repaired"], attempt["failed"]
    else:
        report = readiness.inspect(root, deep=deep)
    state = str(report["execution_readiness"])
    requirements = _requirements(report)
    unavailable: list[str] = []
    if state == "READY":
        mode, reason = "FULL", "every requirement is met; the full workflow is available"
    elif state == "DEGRADED":
        mode = "DEGRADED"
        reason = report["reason"]
        unavailable = list(ORCHESTRATION)
    else:
        # PARTIAL survives here only when a repair could not close it, which makes it a
        # blocker rather than a gap: continuing would claim a workflow that is not there.
        mode, reason = "BLOCKED", report["reason"]
    git = next(item for item in requirements if item["requirement"] == "git")
    if mode != "BLOCKED" and git["status"] != "PASS":
        unavailable = [*unavailable, *NEEDS_GIT]
    return {
        "root": str(root),
        "mode": mode,
        "reason": reason,
        "requirements": requirements,
        "repaired": repaired,
        "failed": failed,
        "unavailable": unavailable,
        # Degraded work is safe to do and unsafe to describe as the full workflow. A caller
        # that requires orchestration has to stop here, which `requires` answers.
        "safe_to_proceed": mode != "BLOCKED",
        "readiness": report,
        "status": "PASS" if mode == "FULL" else "FAIL",
    }


def for_plane(plane: Any, *, repair_first: bool = True, deep: bool = True) -> dict[str, Any]:
    """The preflight of an open plane's project.

    The versioned API reaches it this way. Opening a plane already requires an adopted
    project, so the case where the control plane does not exist yet is served by the command
    line, which runs the preflight before there is anything to open.
    """

    return run(plane.root, repair_first=repair_first, deep=deep)


def requires(result: dict[str, Any], *, orchestration: bool = True, git: bool = False) -> None:
    """Refuse the work when the mode cannot support what it needs.

    Called by an operation that cannot honestly run without orchestration or without git:
    better a refusal naming the missing piece than a task record nothing enforces.
    """

    from .contracts import require

    require(result["mode"] != "BLOCKED", "NOT_READY", f"Execution is blocked: {result['reason']}")
    if orchestration:
        require(
            result["mode"] == "FULL",
            "DEGRADED_MODE",
            f"This needs the full workflow, which is unavailable: {result['reason']}",
        )
    if git:
        state = next(item for item in result["requirements"] if item["requirement"] == "git")
        require(
            state["status"] == "PASS",
            "NOT_READY",
            f"This needs a git working tree: {state['detail']}",
        )


def render(result: dict[str, Any]) -> str:
    """The report a person reads, which never hides a degraded mode."""

    lines = [f"Execution mode: {result['mode']}", ""]
    width = max(len(str(item["requirement"])) for item in result["requirements"])
    for item in result["requirements"]:
        lines.append(f"  {str(item['requirement']):<{width}}  {item['status']}")
    lines += ["", f"Reason: {result['reason']}"]
    if result["repaired"]:
        lines += ["", "Repaired automatically:"]
        lines += [f"  - {entry['action']}: {entry['outcome']}" for entry in result["repaired"]]
    if result["failed"]:
        lines += ["", "Could not repair:"]
        lines += [f"  ! {entry['action']}: {entry['outcome']}" for entry in result["failed"]]
    if result["unavailable"]:
        lines += ["", "Unavailable:"]
        lines += [f"  - {item}" for item in result["unavailable"]]
    # A requirement that is only unmet because another one is has already been explained by
    # that other one; repeating it three times reads as three problems instead of one.
    explained = {item["requirement"] for item in result["requirements"] if item["status"] != "PASS"}
    outstanding = [
        item
        for item in result["requirements"]
        if item["status"] not in {"PASS", "OFF"}
        and not item["advisory"]
        and item["caused_by"] not in explained
    ]
    if outstanding:
        lines += ["", "Outstanding:"]
        for item in outstanding:
            lines.append(f"  - {item['requirement']} ({item['status']}): {item['detail']}")
            if item["repair"]:
                lines.append(f"    Repair: {item['repair']}")
    lines += [
        "",
        "Proceeding is safe for the work this mode supports."
        if result["safe_to_proceed"]
        else "Do not proceed: the workflow this project claims is not available.",
    ]
    return "\n".join(lines)
