"""The project status document, section by section.

Agents and the console read ``Plane.status()`` to decide what to work on. The
scenario below is built so every count differs from what an inverted condition,
a swapped key or a wrong store kind would produce.
"""

from __future__ import annotations

from typing import Any

from conftest import checkpoint, contract
from test_kernel import entity

from agentic_discipline.control.api import call
from agentic_discipline.control.verification import complete, verify

FRESHNESS_NOTE = (
    "Proof is checked against current measured files and artifacts. "
    "Reconcile also refreshes discovery."
)
STATUS_KEYS = [
    "project",
    "knowledge_version",
    "task_counts",
    "tasks",
    "agents",
    "leases",
    "evidence",
    "requirements",
    "evolution",
    "metrics",
    "knowledge",
    "claims",
    "decisions",
    "audit",
    "freshness_note",
]


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


def _scenario(project: Any) -> dict[str, str]:
    # A source file that disappears leaves a stale, historical code entity behind.
    (project.root / "extra.py").write_text("extra = 1\n")
    project.reconcile()
    (project.root / "extra.py").unlink()
    project.reconcile()

    orders, legacy, rename, keep = project.knowledge.apply(
        [
            entity("Orders"),
            entity("Legacy"),
            {**entity("Rename module"), "graph": "evolution"},
            {**entity("Keep local data"), "graph": "decision", "authority": "human"},
        ],
        project.store.knowledge_version,
        "status scenario",
    )["entities"]
    project.knowledge.lifecycle(legacy["id"], "RETIRED", "requirement withdrawn")

    worker = project.join("worker", ["code", "terminal"])["session"]
    data = {**contract(), "requirements": [orders["id"]]}
    project.approve_command(data["verification"][0]["command"])
    done = project.create_task(data)["id"]
    project.ready(done)
    project.claim(done, worker)
    project.checkpoint(done, worker, checkpoint())
    assert verify(project, done, worker)["status"] == "PASS"
    complete(project, done, worker)

    # Two tasks are blocked; the owner resolves one, which records a decision and
    # leaves exactly one open blocker.
    blocked = []
    for question in ("Choose a retention period", "Choose an archive format"):
        task_id = project.create_task(contract())["id"]
        project.ready(task_id)
        project.claim(task_id, worker)
        project.release(task_id, worker, question)
        blocked.append(task_id)
    call(project, "resolve_blocker", {"task_id": blocked[1], "decision": "Parquet"}, local=True)
    project.create_task(contract())
    project.create_task(contract())

    # A human claim on a verified requirement correctly forces revalidation, so the
    # conflicting pair targets the evolution item and the completed task stays current.
    project.knowledge.claim(_claim(rename["id"], 30, "first brief"))
    project.knowledge.claim(_claim(rename["id"], 60, "second brief"))
    return {
        "orders": orders["id"],
        "legacy": legacy["id"],
        "rename": rename["id"],
        "keep": keep["id"],
    }


def test_status_reports_every_section_of_the_project(project: Any) -> None:
    ids = _scenario(project)

    status = project.status()

    store = project.store
    tasks = store.list("task")
    entities = store.list("entity")
    evidence = store.list("evidence")
    assert list(status) == STATUS_KEYS
    assert status["project"] == store.list("project")[0]
    assert status["knowledge_version"] == store.knowledge_version
    assert status["task_counts"] == {"BLOCKED": 2, "COMPLETED": 1, "PLANNED": 2}
    assert status["tasks"] == tasks

    agents = store.list("agent")
    assert agents and all("session_hash" in agent for agent in agents)
    assert status["agents"] == [
        {key: value for key, value in agent.items() if key != "session_hash"} for agent in agents
    ]
    leases = store.list("lease")
    assert leases and status["leases"] == leases
    assert evidence and status["evidence"] == evidence

    assert [item["id"] for item in status["requirements"]] == [ids["orders"]]
    evolution = {item["id"] for item in status["evolution"]}
    assert {ids["legacy"], ids["rename"]} <= evolution
    assert not {ids["orders"], ids["keep"]} & evolution
    assert evolution == {
        item["id"]
        for item in entities
        if item["lifecycle"] != "ACTIVE" or item["graph"] == "evolution"
    }

    assert status["metrics"] == {
        "verification": {"verified": 1, "total": 1},
        "evidence_currency": {"current": len(evidence), "total": len(evidence)},
        "decision_debt": {"task_blockers": 1, "conflicting_claims": 2},
    }
    stale = sum(bool(item.get("stale")) for item in entities)
    historical = sum(item["lifecycle"] != "ACTIVE" for item in entities)
    active = len(entities) - historical
    assert stale >= 1 and historical >= 2 and active not in {historical, stale}
    assert status["knowledge"] == {"active": active, "stale": stale, "historical": historical}

    assert status["claims"] == store.list("claim")
    recorded = store.list("decision")
    assert recorded
    assert [item["id"] for item in status["decisions"]] == [ids["keep"]] + [
        item["id"] for item in recorded
    ]
    assert status["audit"] == store.audit()
    assert status["freshness_note"] == FRESHNESS_NOTE
