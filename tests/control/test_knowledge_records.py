"""Knowledge links, claims, claim resolutions and checkpoints, record by record.

These records are the provenance trail an agent reasons from: which knowledge
depends on what, which statements conflict, who resolved them, and where work
stopped. Existing tests checked dispositions or single fields, so an edge could
lose its audit event, a conflict could be missed, or a resolution could be
recorded without its decision. Each case compares the written records whole.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest
from conftest import checkpoint, contract
from test_kernel import entity
from test_workspaces import repository

from agentic_discipline.common import run_git
from agentic_discipline.control.contracts import ControlError, digest
from agentic_discipline.control.discovery import fingerprint
from agentic_discipline.control.plane import Plane
from agentic_discipline.control.verification import verify


def _nodes(project: Any, *changes: dict[str, Any]) -> list[dict[str, Any]]:
    return project.knowledge.apply(list(changes), project.store.knowledge_version, "setup")[
        "entities"
    ]


def _force(project: Any, kind: str, identifier: str, **fields: Any) -> dict[str, Any]:
    with project.store.transaction():
        current = project.store.get(identifier, kind)
        return project.store.put(kind, {**current, **fields}, expected=current["version"])


def _events(project: Any, action: str) -> list[dict[str, Any]]:
    rows = project.store.db.execute(
        "SELECT actor, action, payload FROM events WHERE action = ? ORDER BY seq", (action,)
    )
    return [{"actor": r["actor"], "payload": json.loads(r["payload"])} for r in rows]


def _writer(project: Any, record: dict[str, Any]) -> str:
    kind = project.store.db.execute(
        "SELECT kind FROM records WHERE id = ?", (record["id"],)
    ).fetchone()["kind"]
    (event,) = [
        e
        for e in _events(project, f"{kind}.write")
        if e["payload"]["id"] == record["id"] and e["payload"]["version"] == record["version"]
    ]
    return event["actor"]


def _claim(subject: str, **changes: Any) -> dict[str, Any]:
    return {
        "subject": subject,
        "predicate": "retention_days",
        "value": 30,
        "source_ref": "brief.md",
        "authority": "human",
        "confidence": 1,
        "observation": "DECLARED",
        **changes,
    }


# --- Knowledge.link -----------------------------------------------------------------------


def test_new_link_is_recorded_audited_and_versioned(project: Any) -> None:
    source, target = _nodes(project, entity("dependent"), entity("upstream"))
    version = project.store.knowledge_version

    edge = project.knowledge.link(source["id"], target["id"], "depends_on")

    assert edge["id"].startswith("EDGE-")
    assert edge == {
        "id": edge["id"],
        "source": source["id"],
        "target": target["id"],
        "relation": "depends_on",
    }
    row = project.store.db.execute("SELECT * FROM edges WHERE id = ?", (edge["id"],)).fetchone()
    assert dict(row) == edge
    assert project.store.knowledge_version == version + 1
    assert _events(project, "edge.add")[-1] == {"actor": "local", "payload": edge}


def test_repeated_link_returns_the_existing_edge_without_new_writes(project: Any) -> None:
    source, target = _nodes(project, entity("dependent"), entity("upstream"))
    first = project.knowledge.link(source["id"], target["id"], "depends_on")
    version, events = project.store.knowledge_version, len(_events(project, "edge.add"))

    assert project.knowledge.link(source["id"], target["id"], "depends_on") == first
    assert (project.store.knowledge_version, len(_events(project, "edge.add"))) == (version, events)


@pytest.mark.parametrize(
    ("relation", "graph"),
    [
        ("implemented_by", "code"),
        ("verified_by", "evidence"),
        ("claimed_by", "execution"),
        ("evidenced_by", "evidence"),
        ("blocked_by", "decision"),
    ],
)
def test_typed_relations_accept_only_their_target_graph(
    project: Any, relation: str, graph: str
) -> None:
    source, right, wrong = _nodes(
        project,
        entity("requirement"),
        {**entity("target"), "graph": graph},
        {**entity("other"), "graph": "architecture"},
    )
    assert project.knowledge.link(source["id"], right["id"], relation)["relation"] == relation
    with pytest.raises(ControlError) as caught:
        project.knowledge.link(source["id"], wrong["id"], relation)
    assert (caught.value.code, str(caught.value)) == (
        "INVALID_EDGE",
        "Relationship target belongs to a different graph",
    )


def test_historical_knowledge_may_depend_on_historical_knowledge(project: Any) -> None:
    left, right = _nodes(project, entity("old dependent"), entity("old upstream"))
    project.knowledge.lifecycle(left["id"], "RETIRED", "gone")
    project.knowledge.lifecycle(right["id"], "RETIRED", "gone")
    assert project.knowledge.link(left["id"], right["id"], "depends_on")["relation"] == "depends_on"


# --- Knowledge.claim ----------------------------------------------------------------------


def test_first_claim_is_a_candidate_with_its_statement(project: Any) -> None:
    (subject,) = _nodes(project, entity("Orders"))
    data = _claim(subject["id"], authority="documentation", predicate=7)
    claim = project.knowledge.claim(data)
    assert {k: v for k, v in claim.items() if k not in {"id", "version"}} == {
        **data,
        "conflicts": [],
        "disposition": "CANDIDATE",
    }


def test_claims_about_unknown_subjects_are_rejected(project: Any) -> None:
    project.approve_command(contract()["verification"][0]["command"])
    task = project.create_task(contract())["id"]
    with pytest.raises(ControlError) as caught:
        project.knowledge.claim(_claim(task))
    assert (caught.value.code, str(caught.value)) == ("NOT_FOUND", f"Record not found: {task}")


def test_only_live_differing_statements_about_the_same_fact_conflict(project: Any) -> None:
    subject, other = _nodes(project, entity("Orders"), entity("Invoices"))
    doc = {"authority": "documentation"}
    live = project.knowledge.claim(_claim(subject["id"], value=30, **doc))
    same_value = project.knowledge.claim(_claim(subject["id"], value=30, source_ref="copy", **doc))
    project.knowledge.claim(_claim(subject["id"], predicate="archive_days", value=1, **doc))
    project.knowledge.claim(_claim(other["id"], value=90, **doc))
    retired = project.knowledge.claim(_claim(subject["id"], value=45, **doc))
    _force(project, "claim", retired["id"], disposition="SUPERSEDED")
    rejected = project.knowledge.claim(_claim(subject["id"], value=50, **doc))
    _force(project, "claim", rejected["id"], disposition="REJECTED")

    newcomer = project.knowledge.claim(_claim(subject["id"], value=60, **doc))
    assert sorted(newcomer["conflicts"]) == sorted([live["id"], same_value["id"]])
    assert newcomer["disposition"] == "CONFLICTING"
    for existing in (live, same_value):
        updated = project.store.get(existing["id"], "claim")
        assert (updated["disposition"], newcomer["id"] in updated["conflicts"]) == (
            "CONFLICTING",
            True,
        )


def test_stronger_authority_supersedes_and_weaker_is_rejected(project: Any) -> None:
    (subject,) = _nodes(project, entity("Orders"))
    weak = project.knowledge.claim(_claim(subject["id"], value=30, authority="documentation"))
    code = project.knowledge.claim(_claim(subject["id"], value=45, authority="code"))
    strong = project.knowledge.claim(_claim(subject["id"], value=60, authority="human"))

    assert strong["disposition"] == "CANONICAL"
    assert sorted(strong["conflicts"]) == sorted([weak["id"], code["id"]])
    for superseded, earlier in ((weak, [code["id"]]), (code, [weak["id"]])):
        stored = project.store.get(superseded["id"], "claim")
        assert stored["disposition"] == "SUPERSEDED"
        # Conflicts recorded earlier are kept when the new one is added.
        assert sorted(stored["conflicts"]) == sorted([*earlier, strong["id"]])

    late = project.knowledge.claim(_claim(subject["id"], value=90, authority="documentation"))
    assert late["disposition"] == "REJECTED"
    # A stronger existing claim is not rewritten by a weaker newcomer.
    assert project.store.get(strong["id"], "claim")["version"] == strong["version"]


def test_verified_claim_rejects_stale_evidence(project: Any) -> None:
    (requirement,) = _nodes(project, entity("Orders"))
    data = {**contract(), "requirements": [requirement["id"]]}
    project.approve_command(data["verification"][0]["command"])
    task = project.create_task(data)["id"]
    project.ready(task)
    session = project.join("worker", ["code", "terminal"])["session"]
    project.claim(task, session)
    project.checkpoint(task, session, checkpoint())
    (proof,) = verify(project, task, session)["evidence"]
    _force(project, "evidence", proof["id"], stale=True)

    with pytest.raises(ControlError) as caught:
        project.knowledge.claim(
            _claim(
                requirement["id"],
                observation="VERIFIED",
                evidence_refs=[proof["id"]],
                acceptance_index=0,
            )
        )
    assert (caught.value.code, str(caught.value)) == (
        "UNPROVEN_CLAIM",
        "Claim evidence is not current or its artifact was changed",
    )


# --- Knowledge.resolve_claim --------------------------------------------------------------


def test_resolution_promotes_the_claim_supersedes_rivals_and_records_the_decision(
    project: Any,
) -> None:
    (subject,) = _nodes(project, entity("Orders"))
    chosen = project.knowledge.claim(
        _claim(subject["id"], value=30, authority="code", evidence_refs=[])
    )
    rival = project.knowledge.claim(_claim(subject["id"], value=60, authority="code"))
    unrelated = project.knowledge.claim(_claim(subject["id"], predicate="archive_days"))
    chosen = project.store.get(chosen["id"], "claim")

    resolved = project.knowledge.resolve_claim(chosen["id"], "Owner confirmed thirty days")

    assert {k: v for k, v in resolved.items() if k not in {"id", "version"}} == {
        **{k: v for k, v in chosen.items() if k not in {"id", "version"}},
        "disposition": "CANONICAL",
        "original_authority": "code",
        "authority": "human",
        "observation": "DECLARED",
        "evidence_refs": [],
        "resolution_reason": "Owner confirmed thirty days",
    }
    assert _writer(project, resolved) == "local-owner"
    superseded = project.store.get(rival["id"], "claim")
    assert superseded["disposition"] == "SUPERSEDED"
    assert _writer(project, superseded) == "local-owner"
    assert project.store.get(unrelated["id"], "claim") == unrelated

    (decision,) = project.store.list("decision")
    assert {k: v for k, v in decision.items() if k not in {"id", "version"}} == {
        "claim_id": chosen["id"],
        "reason": "Owner confirmed thirty days",
        "state": "DECIDED",
        "authority": "human",
    }
    assert _writer(project, decision) == "local-owner"


def test_resolution_refuses_a_stale_subject(project: Any) -> None:
    (subject,) = _nodes(project, entity("Orders"))
    claim = project.knowledge.claim(_claim(subject["id"], authority="documentation"))
    _force(project, "entity", subject["id"], stale=True)
    with pytest.raises(ControlError) as caught:
        project.knowledge.resolve_claim(claim["id"], "Confirmed")
    assert (caught.value.code, str(caught.value)) == (
        "STALE_CONTEXT",
        "Cannot promote retired or stale intent",
    )


# --- Plane.checkpoint ---------------------------------------------------------------------


def test_checkpoint_payload_captures_where_work_stopped(tmp_path: Path) -> None:
    repository(tmp_path)
    with Plane(tmp_path) as plane:
        data = contract()
        plane.approve_command(data["verification"][0]["command"])
        task = plane.create_task(data)["id"]
        other = plane.create_task(contract())["id"]
        plane.ready(task)
        session = plane.join("worker", ["code", "terminal"])["session"]
        lease = plane.claim(task, session)
        (own,) = verify(plane, task, session)["evidence"]
        with plane.store.transaction():
            plane.store.put("evidence", {**own, "id": None, "task_id": other})

        started = time.time()
        saved = plane.checkpoint(task, session, checkpoint())

        payload = saved["payload"]
        current = plane.store.get(task, "task")
        assert {k: v for k, v in payload.items() if k != "timestamp"} == {
            **checkpoint(),
            "task_id": task,
            "agent_id": lease["agent_id"],
            "objective": current["objective"],
            "execution_phase": current["state"],
            "branch": run_git(["branch", "--show-current"], cwd=tmp_path).strip(),
            "workspace": str(plane.root),
            "commit": run_git(["rev-parse", "HEAD"], cwd=tmp_path).strip(),
            "knowledge_version": plane.store.knowledge_version,
            "fingerprint": digest(fingerprint(plane.root)),
            "evidence_refs": [own["id"]],
        }
        assert payload["branch"] and payload["commit"]
        assert started <= payload["timestamp"] <= time.time()
        assert (saved["task_id"], saved["content_hash"]) == (task, digest(payload))


def test_equal_human_statements_conflict_instead_of_replacing_each_other(project: Any) -> None:
    (subject,) = _nodes(project, entity("Orders"))
    first = project.knowledge.claim(_claim(subject["id"], value=30))
    assert first["disposition"] == "CANONICAL"
    second = project.knowledge.claim(_claim(subject["id"], value=60))
    assert (second["disposition"], second["conflicts"]) == ("CONFLICTING", [first["id"]])
    assert project.store.get(first["id"], "claim")["disposition"] == "CONFLICTING"


def test_contract_authority_is_canonical_on_its_own(project: Any) -> None:
    (subject,) = _nodes(project, entity("Orders"))
    claim = project.knowledge.claim(_claim(subject["id"], authority="contract"))
    assert claim["disposition"] == "CANONICAL"


def test_verified_code_claim_with_current_evidence_is_canonical(project: Any) -> None:
    (requirement,) = _nodes(project, entity("Orders"))
    data = {**contract(), "requirements": [requirement["id"]]}
    project.approve_command(data["verification"][0]["command"])
    task = project.create_task(data)["id"]
    project.ready(task)
    session = project.join("worker", ["code", "terminal"])["session"]
    project.claim(task, session)
    project.checkpoint(task, session, checkpoint())
    (proof,) = verify(project, task, session)["evidence"]

    claim = project.knowledge.claim(
        _claim(
            requirement["id"],
            authority="code",
            observation="VERIFIED",
            evidence_refs=[proof["id"]],
            acceptance_index=0,
        )
    )
    assert claim["disposition"] == "CANONICAL"


def test_checkpoints_reject_credentials(project: Any) -> None:
    project.approve_command(contract()["verification"][0]["command"])
    task = project.create_task(contract())["id"]
    project.ready(task)
    session = project.join("worker", ["code", "terminal"])["session"]
    project.claim(task, session)
    with pytest.raises(ControlError) as caught:
        project.checkpoint(task, session, {**checkpoint(), "next_action": "use password=hunter2"})
    assert (caught.value.code, str(caught.value)) == (
        "SECRET_REJECTED",
        "Possible credential in persistent input",
    )


def _seed_claim(project: Any, identifier: str, subject: str, **changes: Any) -> dict[str, Any]:
    """Insert a claim with a chosen id, so conflict order is deterministic."""
    with project.store.transaction():
        return project.store.put(
            "claim",
            {**_claim(subject, **changes), "id": identifier, "conflicts": []},
        )


def test_every_weaker_conflict_is_updated_even_after_a_stronger_one(project: Any) -> None:
    (subject,) = _nodes(project, entity("Orders"))
    stronger = _seed_claim(
        project, "CLAI-1", subject["id"], value=30, authority="human", disposition="CANONICAL"
    )
    weaker = _seed_claim(
        project,
        "CLAI-2",
        subject["id"],
        value=45,
        authority="documentation",
        disposition="CANDIDATE",
    )

    newcomer = project.knowledge.claim(_claim(subject["id"], value=60, authority="code"))

    # The stronger claim is left untouched; the weaker one, listed after it, is not skipped.
    assert project.store.get(stronger["id"], "claim") == stronger
    updated = project.store.get(weaker["id"], "claim")
    assert (updated["disposition"], updated["conflicts"]) == ("CONFLICTING", [newcomer["id"]])
