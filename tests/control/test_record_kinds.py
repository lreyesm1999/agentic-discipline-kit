"""Identifier kind guards, entry point by entry point.

`Store.get` takes the kind its caller expects and refuses a record of any other
kind, so a task identifier cannot be read as an entity or a claim as a changeset.
Nothing exercised that guard from the outside, leaving every call free to drop the
kind and act on a foreign record. Each case hands an entry point an identifier that
exists under a different kind and pins the refusal.
"""

from __future__ import annotations

from typing import Any, Callable

import pytest
from conftest import contract
from test_kernel import entity

from agentic_discipline.control.contracts import ControlError
from agentic_discipline.control.migration import rollback_changeset
from agentic_discipline.control.verification import proof_current
from agentic_discipline.control.workspaces import cleanup, create_workspace, refresh_workspace

Entry = Callable[[Any, str], Any]

# Each entry point expects one kind; the identifier handed to it names the other.
TASK_ENTRIES: list[tuple[str, Entry]] = [
    ("readiness", lambda project, wrong: project.readiness(wrong)),
    ("ready", lambda project, wrong: project.ready(wrong)),
    ("resolve_blocker", lambda project, wrong: project.resolve_blocker(wrong, "PROCEED")),
    ("claim", lambda project, wrong: project.claim(wrong, _session(project))),
    ("context", lambda project, wrong: project.context(wrong)),
    ("create_workspace", lambda project, wrong: create_workspace(project, wrong)),
    ("cleanup", lambda project, wrong: cleanup(project, wrong)),
    ("refresh_workspace", lambda project, wrong: refresh_workspace(project, wrong)),
    ("transition", lambda project, wrong: project.transition(wrong, "CANCELLED", "why")),
]

ENTITY_ENTRIES: list[tuple[str, Entry]] = [
    ("impact", lambda project, wrong: project.knowledge.impact(wrong)),
    ("lifecycle", lambda project, wrong: project.knowledge.lifecycle(wrong, "DEPRECATED", "why")),
    ("resolve_claim", lambda project, wrong: project.knowledge.resolve_claim(wrong, "why")),
    ("rollback_changeset", lambda project, wrong: rollback_changeset(project, wrong, "why")),
    (
        "link_source",
        lambda project, wrong: project.knowledge.link(wrong, _entity_id(project), "depends_on"),
    ),
    (
        "link_target",
        lambda project, wrong: project.knowledge.link(_entity_id(project), wrong, "depends_on"),
    ),
    (
        # A declared claim re-reads its subject later and would fail the same way, so the
        # first read is only observable on the path that checks evidence in between.
        "claim_subject",
        lambda project, wrong: project.knowledge.claim(
            _claim_data(wrong, observation="VERIFIED", evidence_refs=["EVID-absent"])
        ),
    ),
    (
        "claim_evidence",
        lambda project, wrong: project.knowledge.claim(
            _claim_data(_entity_id(project), observation="VERIFIED", evidence_refs=[wrong])
        ),
    ),
    (
        "apply_identity",
        lambda project, wrong: project.knowledge.apply(
            [{**entity("Orders"), "id": wrong}], project.store.knowledge_version, "why"
        ),
    ),
]


def _claim_data(subject: str, **changes: Any) -> dict[str, Any]:
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


def _session(project: Any) -> str:
    return str(project.join("kind-check", ["code"])["session"])


def _entity_id(project: Any) -> str:
    (created,) = project.knowledge.apply(
        [entity("Orders")], project.store.knowledge_version, "setup"
    )["entities"]
    return str(created["id"])


def _task_id(project: Any) -> str:
    return str(project.create_task(contract())["id"])


def _force(project: Any, kind: str, identifier: str, **fields: Any) -> dict[str, Any]:
    with project.store.transaction():
        current = project.store.get(identifier, kind)
        return project.store.put(kind, {**current, **fields}, expected=current["version"])


def test_proof_of_another_kind_leaves_a_task_unproven(project: Any) -> None:
    # Proof read through a foreign record would be believed rather than refused.
    task = project.create_task(contract())
    foreign = _entity_id(project)
    _force(project, "task", task["id"], state="COMPLETED", proof=[foreign], requirements=[])

    assert proof_current(project, project.store.get(task["id"], "task")) is False


@pytest.mark.parametrize(("name", "call"), TASK_ENTRIES, ids=[n for n, _ in TASK_ENTRIES])
def test_an_entity_identifier_is_refused_where_a_task_is_expected(
    project: Any, name: str, call: Entry
) -> None:
    foreign = _entity_id(project)
    with pytest.raises(ControlError) as caught:
        call(project, foreign)
    assert (caught.value.code, str(caught.value)) == ("NOT_FOUND", f"Record not found: {foreign}")


@pytest.mark.parametrize(("name", "call"), ENTITY_ENTRIES, ids=[n for n, _ in ENTITY_ENTRIES])
def test_a_task_identifier_is_refused_where_another_kind_is_expected(
    project: Any, name: str, call: Entry
) -> None:
    foreign = _task_id(project)
    with pytest.raises(ControlError) as caught:
        call(project, foreign)
    assert (caught.value.code, str(caught.value)) == ("NOT_FOUND", f"Record not found: {foreign}")
