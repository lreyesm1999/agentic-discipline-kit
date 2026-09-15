"""The readiness document, reason by reason.

Agents decide whether to claim a task from ``Plane.readiness``. Existing tests read
only its status, so a reason could lose its type, carry the wrong identifier, or
disappear while the status still said BLOCKED. The blocked task below has every
kind of reason at once, so each entry and its order are pinned.
"""

from __future__ import annotations

from typing import Any

from conftest import contract
from test_kernel import entity


def _force(project: Any, kind: str, identifier: str, **fields: Any) -> dict[str, Any]:
    with project.store.transaction():
        current = project.store.get(identifier, kind)
        return project.store.put(kind, {**current, **fields}, expected=current["version"])


def _claim(subject: str, value: int, source: str) -> dict[str, Any]:
    return {
        "subject": subject,
        "predicate": "retention_days",
        "value": value,
        "source_ref": source,
        "authority": "human",
        "confidence": 1,
        "observation": "DECLARED",
    }


def test_blocked_task_lists_every_reason_in_order(project: Any) -> None:
    retired, stale, disputed, unrelated = project.knowledge.apply(
        [
            entity("Retired rule"),
            entity("Stale rule"),
            entity("Disputed rule"),
            entity("Unrelated rule"),
        ],
        project.store.knowledge_version,
        "readiness scenario",
    )["entities"]
    # Conflicts about knowledge the task does not require must not block it.
    project.knowledge.claim(_claim(unrelated["id"], 1, "other brief"))
    project.knowledge.claim(_claim(unrelated["id"], 2, "another brief"))
    dependency = project.create_task(contract())["id"]  # planned, so it has no current proof
    command = contract()["verification"][0]["command"]
    blocked = project.create_task(
        {
            **contract(),
            "requirements": [retired["id"], stale["id"], disputed["id"]],
            "dependencies": [dependency],
            "assumptions": ["the cache is warm"],
        }
    )["id"]

    project.knowledge.lifecycle(retired["id"], "RETIRED", "withdrawn")
    _force(project, "entity", stale["id"], stale=True)
    project.knowledge.claim(_claim(disputed["id"], 30, "first brief"))
    project.knowledge.claim(_claim(disputed["id"], 60, "second brief"))
    _force(project, "task", blocked, blocker="Choose a retention period")

    conflicts = [
        claim["id"]
        for claim in project.store.list("claim")
        if claim["subject"] == disputed["id"] and claim["disposition"] == "CONFLICTING"
    ]
    assert len(conflicts) == 2
    assert project.readiness(blocked) == {
        "task_id": blocked,
        "status": "BLOCKED",
        "reasons": [
            {"type": "dependency", "id": dependency},
            {"type": "knowledge", "id": retired["id"]},
            {"type": "knowledge", "id": stale["id"]},
            {"type": "unapproved_command", "command": command},
            *({"type": "conflict", "id": identifier} for identifier in conflicts),
            {"type": "human", "reason": "Choose a retention period"},
        ],
        "assumptions": ["the cache is warm"],
    }


def test_unblocked_tasks_report_ready_with_or_without_assumptions(project: Any) -> None:
    project.approve_command(contract()["verification"][0]["command"])
    assumed = project.create_task({**contract(), "assumptions": ["the cache is warm"]})["id"]
    plain = project.create_task(contract())["id"]

    assert project.readiness(assumed) == {
        "task_id": assumed,
        "status": "READY_WITH_MANAGED_UNCERTAINTY",
        "reasons": [],
        "assumptions": ["the cache is warm"],
    }
    assert project.readiness(plain) == {
        "task_id": plain,
        "status": "READY",
        "reasons": [],
        "assumptions": [],
    }
