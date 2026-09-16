"""Knowledge and task-lifecycle rules asserted by exact error code and message.

Agents recover from control-plane refusals by branching on ``ControlError.code``.
Most existing tests only asserted that some ControlError was raised, so a rule
could report the wrong code, lose its message, or stop firing without a failure.
Each case breaks one rule on an otherwise valid project and asserts the exact
outcome, plus the boundary values the rule must still accept.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from conftest import checkpoint, contract
from test_kernel import entity

from agentic_discipline.control.contracts import ControlError
from agentic_discipline.control.verification import verify


def _rejects(code: str, message: str, action: Any, *args: Any, **kwargs: Any) -> None:
    with pytest.raises(ControlError) as caught:
        action(*args, **kwargs)
    assert (caught.value.code, str(caught.value)) == (code, message)


def _force(project: Any, kind: str, identifier: str, **fields: Any) -> dict[str, Any]:
    """Put a record into a state that is expensive to reach through the workflow."""
    with project.store.transaction():
        current = project.store.get(identifier, kind)
        return project.store.put(kind, {**current, **fields}, expected=current["version"])


def _nodes(project: Any, *names: str, **overrides: Any) -> list[dict[str, Any]]:
    changes = [{**entity(name), **overrides} for name in names]
    return project.knowledge.apply(changes, project.store.knowledge_version, "setup")["entities"]


def _task(project: Any, approve: bool = True, **changes: Any) -> str:
    data = {**contract(), **changes}
    if approve:
        project.approve_command(data["verification"][0]["command"])
    return project.create_task(data)["id"]


def _ready_task(project: Any, **changes: Any) -> str:
    task = _task(project, **changes)
    project.ready(task)
    return task


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


# --- Knowledge.apply ----------------------------------------------------------------------


def test_changeset_needs_a_reason_and_changes(project: Any) -> None:
    version = project.store.knowledge_version
    message = "Reason and changes are required"
    _rejects("INVALID_CHANGESET", message, project.knowledge.apply, [entity()], version, "  ")
    _rejects("INVALID_CHANGESET", message, project.knowledge.apply, [], version, "reason")


def test_changeset_on_a_stale_version_is_rejected(project: Any) -> None:
    _rejects(
        "VERSION_CONFLICT",
        "Knowledge version changed; reconcile before retry",
        project.knowledge.apply,
        [entity()],
        project.store.knowledge_version + 1,
        "late",
    )


def test_retired_identity_cannot_be_reactivated_but_active_one_can_change(project: Any) -> None:
    active, retired = _nodes(project, "Orders", "Legacy")
    project.knowledge.lifecycle(retired["id"], "RETIRED", "withdrawn")
    current = project.store.get(active["id"], "entity")
    renamed = project.knowledge.apply(
        [{**current, "name": "Orders v2", "expected_version": current["version"]}],
        project.store.knowledge_version,
        "rename",
    )
    assert renamed["entities"][0]["name"] == "Orders v2"

    old = project.store.get(retired["id"], "entity")
    _rejects(
        "RESURRECTION_BLOCKED",
        "Retired identities cannot be implicitly reactivated; create an explicit reviewed replacement",
        project.knowledge.apply,
        [{**old, "lifecycle": "ACTIVE", "expected_version": old["version"]}],
        project.store.knowledge_version,
        "revive",
    )


def test_retiring_knowledge_with_active_dependents_is_rejected(project: Any) -> None:
    upstream, dependent = _nodes(project, "upstream", "dependent")
    project.knowledge.link(dependent["id"], upstream["id"], "depends_on")
    _rejects(
        "RETIRED_DEPENDENCY",
        "Retire or replace active dependents in the same changeset",
        project.knowledge.lifecycle,
        upstream["id"],
        "RETIRED",
        "removed",
    )


# --- Knowledge.link -----------------------------------------------------------------------


def test_link_rejects_unknown_relations_and_self_edges(project: Any) -> None:
    left, right = _nodes(project, "left", "right")
    message = "Unknown relation or self edge"
    _rejects("INVALID_EDGE", message, project.knowledge.link, left["id"], right["id"], "relates_to")
    _rejects("INVALID_EDGE", message, project.knowledge.link, left["id"], left["id"], "depends_on")


def test_active_knowledge_cannot_depend_on_retired_knowledge(project: Any) -> None:
    active, retired = _nodes(project, "active", "retired")
    project.knowledge.lifecycle(retired["id"], "RETIRED", "gone")
    _rejects(
        "RETIRED_DEPENDENCY",
        "Active knowledge cannot depend on retired knowledge",
        project.knowledge.link,
        active["id"],
        retired["id"],
        "depends_on",
    )


def test_dependency_cycles_are_rejected(project: Any) -> None:
    first, second, third = _nodes(project, "first", "second", "third")
    project.knowledge.link(first["id"], second["id"], "depends_on")
    project.knowledge.link(second["id"], third["id"], "depends_on")
    _rejects(
        "CYCLE", "Dependency cycle", project.knowledge.link, third["id"], first["id"], "depends_on"
    )


def test_typed_relations_require_a_target_from_their_graph(project: Any) -> None:
    (requirement,) = _nodes(project, "requirement")
    (other,) = _nodes(project, "other requirement")
    (module,) = _nodes(project, "module", graph="code")
    edge = project.knowledge.link(requirement["id"], module["id"], "implemented_by")
    assert edge["relation"] == "implemented_by"
    _rejects(
        "INVALID_EDGE",
        "Relationship target belongs to a different graph",
        project.knowledge.link,
        requirement["id"],
        other["id"],
        "implemented_by",
    )


# --- Knowledge.query and impact -----------------------------------------------------------


def test_query_accepts_its_boundaries(project: Any) -> None:
    _nodes(project, "Orders")
    version = project.store.knowledge_version
    for kwargs in ({"limit": 1}, {"limit": 500}, {"graph": "code"}, {"at_version": 0}):
        assert isinstance(project.knowledge.query(**kwargs), list)
    assert project.knowledge.query("Orders", at_version=version)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"limit": 0}, "Invalid graph or limit"),
        ({"limit": 501}, "Invalid graph or limit"),
        ({"graph": "unknown"}, "Invalid graph or limit"),
        ({"at_version": -1}, "Unknown knowledge revision"),
        ({"at_version": True}, "Unknown knowledge revision"),
        ({"at_version": 10**9}, "Unknown knowledge revision"),
    ],
    ids=["limit-0", "limit-501", "unknown-graph", "negative-rev", "bool-rev", "future-rev"],
)
def test_query_rejects_invalid_arguments(
    project: Any, kwargs: dict[str, Any], message: str
) -> None:
    _rejects("INVALID_QUERY", message, project.knowledge.query, **kwargs)


def test_impact_traversal_bounds(project: Any) -> None:
    (node,) = _nodes(project, "Orders")
    assert project.knowledge.impact(node["id"], "out", 0) == []
    assert project.knowledge.impact(node["id"], "in", 20) == []
    for direction, depth in (("both", 4), ("in", -1), ("out", 21)):
        _rejects(
            "INVALID_QUERY",
            "Invalid traversal",
            project.knowledge.impact,
            node["id"],
            direction,
            depth,
        )


# --- Knowledge.claim, resolve_claim and lifecycle -----------------------------------------


def test_claims_need_provenance_and_verified_ones_need_evidence(project: Any) -> None:
    (node,) = _nodes(project, "Orders")
    incomplete = _claim_data(node["id"])
    del incomplete["source_ref"]
    _rejects(
        "INVALID_CLAIM",
        "Claim lacks provenance or statement",
        project.knowledge.claim,
        incomplete,
    )
    message = "Verified claims require evidence references"
    verified = _claim_data(node["id"], observation="VERIFIED")
    _rejects("UNPROVEN_CLAIM", message, project.knowledge.claim, verified)
    _rejects("UNPROVEN_CLAIM", message, project.knowledge.claim, {**verified, "evidence_refs": []})


def test_verified_claims_must_cite_current_evidence_for_their_requirement(project: Any) -> None:
    requirement, unrelated = _nodes(project, "Orders", "Unrelated")
    task = _ready_task(project, requirements=[requirement["id"]])
    session = project.join("worker", ["code", "terminal"])["session"]
    project.claim(task, session)
    project.checkpoint(task, session, checkpoint())
    proof = verify(project, task, session)["evidence"][0]
    claim = _claim_data(
        requirement["id"], observation="VERIFIED", evidence_refs=[proof["id"]], acceptance_index=0
    )

    message = "Claim must cite an acceptance criterion for its requirement"
    _rejects(
        "UNRELATED_EVIDENCE",
        message,
        project.knowledge.claim,
        {**claim, "subject": unrelated["id"]},
    )
    _rejects(
        "UNRELATED_EVIDENCE", message, project.knowledge.claim, {**claim, "acceptance_index": 1}
    )
    assert project.knowledge.claim(claim)["disposition"] == "CANONICAL"

    (project.root / "app.py").write_text("value = 1\n# changed after proof\n")
    _rejects(
        "UNPROVEN_CLAIM",
        "Claim evidence is not current or its artifact was changed",
        project.knowledge.claim,
        {**claim, "predicate": "archive_days"},
    )


def test_claim_resolution_needs_a_decision_and_current_subject(project: Any) -> None:
    (node,) = _nodes(project, "Orders")
    claim = project.knowledge.claim(_claim_data(node["id"], authority="documentation"))
    _rejects(
        "DECISION_REQUIRED",
        "Claim resolution needs an owner decision",
        project.knowledge.resolve_claim,
        claim["id"],
        "  ",
    )
    project.knowledge.lifecycle(node["id"], "RETIRED", "withdrawn")
    _rejects(
        "STALE_CONTEXT",
        "Cannot promote retired or stale intent",
        project.knowledge.resolve_claim,
        claim["id"],
        "Confirmed",
    )


@pytest.mark.parametrize(
    ("state", "reason"), [("ACTIVE", "reason"), ("RETIRED", "  "), ("GONE", "reason")]
)
def test_lifecycle_needs_a_non_active_state_and_reason(
    project: Any, state: str, reason: str
) -> None:
    (node,) = _nodes(project, "Orders")
    _rejects(
        "INVALID_LIFECYCLE",
        "A non-active state and reason are required",
        project.knowledge.lifecycle,
        node["id"],
        state,
        reason,
    )


# --- Plane: commands, tasks and readiness -------------------------------------------------


@pytest.mark.parametrize("command", [[], ["python", ""], ["python", 3]])
def test_approved_commands_must_be_argv_lists(project: Any, command: list[Any]) -> None:
    _rejects("INVALID_COMMAND", "Use argv", project.approve_command, command)


def test_task_cannot_reference_retired_requirements(project: Any) -> None:
    (node,) = _nodes(project, "Orders")
    project.knowledge.lifecycle(node["id"], "RETIRED", "withdrawn")
    _rejects(
        "STALE_REQUIREMENT",
        "Task refers to inactive or stale knowledge",
        project.create_task,
        {**contract(), "requirements": [node["id"]]},
    )


@pytest.mark.parametrize("state", ["PLANNED", "BLOCKED", "FAILED", "NEEDS_REVALIDATION", "READY"])
def test_ready_accepts_every_recoverable_state(project: Any, state: str) -> None:
    task = _task(project)
    _force(project, "task", task, state=state)
    assert project.ready(task)["state"] == "READY"


@pytest.mark.parametrize("state", ["CLAIMED", "COMPLETED", "CANCELLED"])
def test_ready_rejects_active_and_terminal_states(project: Any, state: str) -> None:
    task = _task(project)
    _force(project, "task", task, state=state)
    _rejects("INVALID_TRANSITION", "Task cannot become ready", project.ready, task)


def test_ready_requires_no_readiness_blockers(project: Any) -> None:
    task = _task(project, approve=False)
    _rejects("NOT_READY", "Readiness blockers remain", project.ready, task)


def test_resolving_a_blocker_needs_a_decision_and_a_human_blocker(project: Any) -> None:
    task = _ready_task(project)
    _rejects(
        "DECISION_REQUIRED",
        "Record the decision that resolves the blocker",
        project.resolve_blocker,
        task,
        "  ",
    )
    message = "Task has no human blocker"
    _rejects("NOT_BLOCKED", message, project.resolve_blocker, task, "Thirty days")
    _force(project, "task", task, state="BLOCKED", blocker=None)
    _rejects("NOT_BLOCKED", message, project.resolve_blocker, task, "Thirty days")


def test_owner_transitions_need_a_terminal_state_reason_and_an_idle_task(project: Any) -> None:
    task = _ready_task(project)
    reason_message = "Cancellation or supersession needs a reason"
    _rejects("INVALID_TRANSITION", reason_message, project.transition, task, "READY", "why")
    _rejects("INVALID_TRANSITION", reason_message, project.transition, task, "CANCELLED", "  ")

    busy_message = "Task cannot transition while a verifier is active or after terminal disposition"
    _force(project, "task", task, active_run="RUN-1")
    _rejects("INVALID_TRANSITION", busy_message, project.transition, task, "CANCELLED", "stop")
    _force(project, "task", task, active_run=None, state="COMPLETED")
    _rejects("INVALID_TRANSITION", busy_message, project.transition, task, "CANCELLED", "stop")

    other = _ready_task(project)
    assert project.transition(other, "SUPERSEDED", "replaced")["state"] == "SUPERSEDED"


# --- Plane: agents, leases and checkpoints ------------------------------------------------


def test_agents_need_a_name_and_supported_capabilities(project: Any) -> None:
    message = "Name and supported capabilities required"
    _rejects("INVALID_AGENT", message, project.join, "  ", ["code"])
    _rejects("INVALID_AGENT", message, project.join, "worker", [])
    _rejects("INVALID_AGENT", message, project.join, "worker", ["code", "hacking"])
    every = [
        "code",
        "terminal",
        "frontend",
        "backend",
        "database",
        "security",
        "testing",
        "documentation",
        "browser",
        "code_editing",
    ]
    assert project.join("generalist", every)["session"]


def test_lease_lifetime_bounds(project: Any) -> None:
    task = _ready_task(project)
    session = project.join("worker", ["code", "terminal"])["session"]
    maximum = project.policy()["max_lease_seconds"]
    for seconds in (0, True, maximum + 1):
        _rejects("INVALID_LEASE", "Invalid lease lifetime", project.claim, task, session, seconds)
    assert project.claim(task, session, maximum)["state"] == "ACTIVE"
    for seconds in (0, maximum + 1):
        _rejects(
            "INVALID_LEASE", "Invalid lease lifetime", project.heartbeat, task, session, seconds
        )
    assert project.heartbeat(task, session, maximum)["state"] == "ACTIVE"


def test_claim_requires_a_ready_unblocked_task(project: Any) -> None:
    session = project.join("worker", ["code", "terminal"])["session"]
    planned = _task(project)
    _rejects("NOT_READY", "Task is not available", project.claim, planned, session)
    # READY but still carrying an open human blocker, so readiness reports BLOCKED.
    blocked = _task(project)
    _force(project, "task", blocked, state="READY", blocker="Choose a retention period")
    _rejects("NOT_READY", "Task is not available", project.claim, blocked, session)


def test_claim_requires_the_task_capabilities(project: Any) -> None:
    task = _ready_task(project, capabilities=["database"])
    session = project.join("worker", ["code", "terminal"])["session"]
    _rejects("CAPABILITY_MISMATCH", "Agent lacks task capabilities", project.claim, task, session)


def test_claim_rejects_a_task_that_already_has_an_owner(project: Any) -> None:
    task = _ready_task(project)
    first = project.join("first", ["code", "terminal"])["session"]
    second = project.join("second", ["code", "terminal"])["session"]
    project.claim(task, first)
    _force(project, "task", task, state="READY")
    _rejects("LEASE_CONFLICT", "Task already has an owner", project.claim, task, second)


def test_parallel_claims_without_isolated_workspaces_are_rejected(project: Any) -> None:
    first_task, second_task = _ready_task(project), _ready_task(project)
    first = project.join("first", ["code", "terminal"])["session"]
    second = project.join("second", ["code", "terminal"])["session"]
    project.claim(first_task, first)
    _rejects(
        "PARALLEL_CONFLICT",
        "Concurrent work requires isolated workspaces and disjoint contracts",
        project.claim,
        second_task,
        second,
    )


def test_only_the_lease_owner_may_act_and_release_waits_for_verifiers(project: Any) -> None:
    task = _ready_task(project)
    owner = project.join("owner", ["code", "terminal"])["session"]
    stranger = project.join("stranger", ["code", "terminal"])["session"]
    project.claim(task, owner)
    _rejects("LEASE_LOST", "No active lease owned by this agent", project.heartbeat, task, stranger)
    _force(project, "task", task, active_run="RUN-1")
    _rejects(
        "VERIFICATION_BUSY",
        "Wait for the active verifier before releasing ownership",
        project.release,
        task,
        owner,
    )


def test_checkpoints_need_resumable_context(project: Any) -> None:
    task = _ready_task(project)
    session = project.join("worker", ["code", "terminal"])["session"]
    project.claim(task, session)
    message = "Checkpoint lacks resumable context"
    incomplete = checkpoint()
    del incomplete["failures"]
    _rejects("INVALID_CHECKPOINT", message, project.checkpoint, task, session, incomplete)
    _rejects(
        "INVALID_CHECKPOINT",
        message,
        project.checkpoint,
        task,
        session,
        {**checkpoint(), "next_action": ""},
    )


# --- Plane.context ------------------------------------------------------------------------


def test_context_requires_every_referenced_source(project: Any) -> None:
    task = _task(project, context=["docs/missing.md"])
    _rejects(
        "MISSING_CONTEXT",
        "Required context is missing or stale: docs/missing.md",
        project.context,
        task,
    )


def test_context_rejects_a_tampered_checkpoint(project: Any) -> None:
    task = _ready_task(project)
    session = project.join("worker", ["code", "terminal"])["session"]
    project.claim(task, session)
    saved = project.checkpoint(task, session, checkpoint())
    _force(
        project,
        "checkpoint",
        saved["id"],
        payload={**saved["payload"], "next_action": "Skip verification"},
    )
    _rejects(
        "CHECKPOINT_CORRUPT", "Checkpoint content does not match its hash", project.context, task
    )


def test_context_rejects_retired_requirements(project: Any) -> None:
    (node,) = _nodes(project, "Orders")
    task = _task(project, requirements=[node["id"]])
    project.knowledge.lifecycle(node["id"], "RETIRED", "withdrawn")
    _rejects("STALE_CONTEXT", "Required knowledge is not current", project.context, task)


def test_context_rejects_changed_failure_output(project: Any) -> None:
    task = _ready_task(project)
    session = project.join("worker", ["code", "terminal"])["session"]
    project.claim(task, session)
    project.checkpoint(task, session, checkpoint())
    (project.root / "app.py").write_text("value = 0\n")
    failed = verify(project, task, session)["evidence"][0]
    (project.directory / "evidence" / f"{failed['id']}.json").unlink()
    _rejects("EVIDENCE_CORRUPT", "Failure output was changed or removed", project.context, task)


def test_context_budget_is_never_truncated(project: Any) -> None:
    task = _task(project)
    assert project.context(task, budget=1_000_000)["mandatory"]["task"]["id"] == task
    for budget in (10, True, 1_000_001):
        with pytest.raises(ControlError) as caught:
            project.context(task, budget=budget)
        assert caught.value.code == "CONTEXT_BUDGET"
        assert re.fullmatch(
            r"Mandatory context needs \d+ bytes; never truncate it", str(caught.value)
        )


# --- Valid counterparts -------------------------------------------------------------------
# A rule that fires unconditionally is as broken as one that never fires, so each
# refusal above is paired with the call the same rule must still allow.


def test_knowledge_with_active_dependencies_can_still_change(project: Any) -> None:
    upstream, dependent = _nodes(project, "upstream", "dependent")
    project.knowledge.link(dependent["id"], upstream["id"], "depends_on")
    current = project.store.get(dependent["id"], "entity")
    result = project.knowledge.apply(
        [{**current, "name": "dependent v2", "expected_version": current["version"]}],
        project.store.knowledge_version,
        "rename",
    )
    assert result["entities"][0]["name"] == "dependent v2"


def test_claim_on_an_active_subject_is_resolved_by_the_owner(project: Any) -> None:
    (node,) = _nodes(project, "Orders")
    claim = project.knowledge.claim(_claim_data(node["id"], authority="documentation"))
    resolved = project.knowledge.resolve_claim(claim["id"], "Confirmed thirty days")
    assert (resolved["disposition"], resolved["authority"]) == ("CANONICAL", "human")


def test_idle_owner_releases_with_a_blocker_that_the_owner_resolves(project: Any) -> None:
    task = _ready_task(project)
    session = project.join("worker", ["code", "terminal"])["session"]
    project.claim(task, session)
    released = project.release(task, session, "Choose a retention period")
    assert (released["state"], released["blocker"]) == ("BLOCKED", "Choose a retention period")
    assert project.resolve_blocker(task, "Thirty days")["blocker"] is None


def test_context_carries_referenced_sources_and_intact_failure_output(project: Any) -> None:
    (node,) = _nodes(project, "Orders")
    task = _ready_task(project, context=[node["id"]])
    session = project.join("worker", ["code", "terminal"])["session"]
    project.claim(task, session)
    project.checkpoint(task, session, checkpoint())
    (project.root / "app.py").write_text("value = 0\n")
    assert verify(project, task, session)["status"] == "FAIL"

    mandatory = project.context(task)["mandatory"]
    assert [item["id"] for item in mandatory["required_context"]] == [node["id"]]
    assert [item["evidence"]["result"] for item in mandatory["current_failures"]] == ["FAIL"]
