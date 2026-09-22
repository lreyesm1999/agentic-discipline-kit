"""Put right what can be put right without a decision, and record what was done.

A repair belongs here only when it cannot lose data, cannot change what the project is
supposed to do, needs nothing from outside the machine, and writes only files the kit itself
owns: the payload under `.agentic/`, the managed block inside each adapter file, and the
control directory. Everything else is reported and left alone. In particular, an unexplained
control directory, an altered audit chain and a plane adopted for another checkout are never
repaired: each one needs a person, and guessing would destroy history.

`readiness` decides what is wrong. This decides what may be done about it.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, cast

from . import readiness
from .common import AgenticError

# Ordered by dependency: the payload carries the disciplines the adapters are compiled from,
# the adapters have to be current before a plan is trusted, the plane cannot be adopted
# before the project exists on disk, and the index follows adoption.
ORDER = (
    "installation",
    "disciplines",
    "quality_gates",
    "agent_adapter",
    "control_plane",
    "knowledge",
)


@dataclass(frozen=True)
class Repair:
    """One safe action, with the promise it makes about what it touches."""

    action: str
    writes: tuple[str, ...]
    run: Callable[[Path], str]

    def report(self, outcome: str) -> dict[str, Any]:
        return {"action": self.action, "writes": list(self.writes), "outcome": outcome}


def _reinstall(root: Path) -> str:
    """Fill in what the payload is missing. Existing files are never overwritten.

    `initialize_project` copies without `force`, so a file the project has edited is kept and
    only the absent ones are written. Adoption is left to its own repair.
    """

    from .bootstrap import initialize_project

    result = initialize_project(root, adopt=False)
    written = [a for a in result["actions"] if not str(a).startswith("SKIP")]
    return f"reinstalled the missing payload files ({len(written)} written)"


def _resync(root: Path) -> str:
    from .adapters import detect_adapters, sync_adapters

    result = sync_adapters(root, detect_adapters(root))
    changed = [a for a in cast(list[object], result["actions"]) if not str(a).startswith("SKIP")]
    return f"recompiled the agent surfaces ({len(changed)} file(s) rewritten)"


def _adopt(root: Path) -> str:
    from .control.plane import adopt

    adopt(root)
    return "adopted the repository and indexed the project"


def _reconcile(root: Path) -> str:
    from .control.plane import Plane

    with Plane(root) as plane:
        result = plane.reconcile()
    return f"reindexed the project ({len(result['changed_paths'])} changed path(s))"


PAYLOAD = Repair("reinstall the payload", (".agentic/",), _reinstall)
REPAIRS = {
    "installation": PAYLOAD,
    "disciplines": PAYLOAD,
    "quality_gates": PAYLOAD,
    "agent_adapter": Repair(
        "recompile the agent surfaces", ("AGENTS.md", ".agentic/skills/"), _resync
    ),
    "control_plane": Repair("initialise the control plane", (str(readiness.CONTROL_DIR),), _adopt),
    "knowledge": Repair("reindex the project", (str(readiness.STATE_DB),), _reconcile),
}


def plan(report: dict[str, Any]) -> list[tuple[str, Repair]]:
    """The repairs this report calls for, in dependency order and without repeating one."""

    # A check that is only failing because another one is has no repair of its own: adopting
    # the project restores its record, its index and its orchestration in one action, and when
    # the cause cannot be repaired, attempting the consequence just fails louder.
    outstanding = {
        str(check["name"]): check
        for check in report["checks"]
        if check["status"] in readiness.REPAIRABLE and not check["caused_by"]
    }
    chosen: list[tuple[str, Repair]] = []
    for name in ORDER:
        repair = REPAIRS.get(name)
        if name not in outstanding or repair is None:
            continue
        if any(repair is already for _, already in chosen):
            continue
        chosen.append((name, repair))
    return chosen


def apply(root: Path, *, dry_run: bool = False, deep: bool = True) -> dict[str, Any]:
    """Repair what can be repaired, once, then measure what is left.

    Each repair runs at most once per call. Anything still outstanding afterwards is reported
    rather than retried, because a repair that did not take hold is a finding, not a reason
    to loop.
    """

    root = root.resolve()
    before = readiness.inspect(root, deep=deep)
    chosen = plan(before)
    if dry_run:
        return {
            "root": str(root),
            "dry_run": True,
            "before": before["execution_readiness"],
            "repaired": [],
            "planned": [{**repair.report("would run"), "check": name} for name, repair in chosen],
            "failed": [],
            "readiness": before,
            "status": "PASS",
        }
    repaired: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for name, repair in chosen:
        try:
            outcome = repair.run(root)
        except (AgenticError, OSError, sqlite3.Error) as exc:
            failed.append({**repair.report(f"failed: {exc}"), "check": name})
            continue
        repaired.append({**repair.report(outcome), "check": name})
    after = readiness.inspect(root, deep=deep)
    _record(root, repaired, failed, before, after)
    return {
        "root": str(root),
        "dry_run": False,
        "before": before["execution_readiness"],
        "repaired": repaired,
        "planned": [],
        "failed": failed,
        "readiness": after,
        # A repair run that leaves the project usable is a pass, even when there was nothing
        # to do; one that could not is reported as a failure with what remains.
        "status": "PASS"
        if not failed and after["execution_readiness"] in {"READY", "DEGRADED"}
        else "FAIL",
    }


def _record(
    root: Path,
    repaired: list[dict[str, Any]],
    failed: list[dict[str, Any]],
    before: dict[str, Any],
    after: dict[str, Any],
) -> None:
    """Write what was repaired into the audit chain, when there is one to write to."""

    if not repaired and not failed:
        return
    if not (root / readiness.STATE_DB).is_file():
        return
    from .control.plane import Plane

    try:
        with Plane(root) as plane:
            with plane.store.transaction():
                plane.store.event(
                    "local-owner",
                    "readiness.repair",
                    {
                        "from": before["execution_readiness"],
                        "to": after["execution_readiness"],
                        "repaired": [entry["action"] for entry in repaired],
                        "failed": [entry["action"] for entry in failed],
                    },
                )
    except (AgenticError, OSError, sqlite3.Error):
        # The repair happened; an audit write that cannot land must not undo the report of
        # it. The next readiness check still sees the real state either way.
        return
