"""Knowledge queries and plane operations, outcome by outcome.

Mutation testing found these results were only checked loosely: how many entities
a query returns without a limit, how a query phrase with quotes or punctuation is
matched, whether stale knowledge is hidden, who a policy change is recorded as,
what reconcile reports when nothing changed, the state a released task returns to,
and what resume reports about the workspace. Each case pins the exact result.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from conftest import checkpoint, contract
from test_kernel import entity

from agentic_discipline.control.contracts import ControlError


def _apply(project: Any, *names: str) -> list[dict[str, Any]]:
    applied = project.knowledge.apply(
        [entity(name) for name in names], project.store.knowledge_version, "seed"
    )
    return list(applied["entities"])


def _writers(project: Any, kind: str, record: dict[str, Any]) -> list[str]:
    rows = project.store.db.execute(
        "SELECT actor, payload FROM events WHERE action = ?", (f"{kind}.write",)
    )
    return [
        row["actor"]
        for row in rows
        if json.loads(row["payload"])["id"] == record["id"]
        and json.loads(row["payload"])["version"] == record["version"]
    ]


def _force(project: Any, kind: str, identifier: str, **fields: Any) -> dict[str, Any]:
    with project.store.transaction():
        current = project.store.get(identifier, kind)
        return project.store.put(kind, {**current, **fields}, expected=current["version"])


# --- query ----------------------------------------------------------------------------------


def test_a_query_without_a_limit_returns_fifty_entities(project: Any) -> None:
    _apply(project, *(f"Requirement {index}" for index in range(51)))

    assert len(project.knowledge.query()) == 50
    assert len(project.knowledge.query(limit=51)) == 51


def test_quotes_in_a_query_are_matched_literally(project: Any) -> None:
    (quoted,) = _apply(project, 'Say "hello" to orders')

    assert [e["id"] for e in project.knowledge.query('say "hello"')] == [quoted["id"]]
    # An unpaired quote would end the phrase early and break the search syntax.
    assert [e["id"] for e in project.knowledge.query('say "hello')] == [quoted["id"]]


def test_a_query_matches_words_not_characters(project: Any) -> None:
    # The phrase is matched word by word, so punctuation between words does not matter.
    (hyphenated,) = _apply(project, "orders-api")

    assert [e["id"] for e in project.knowledge.query("orders api")] == [hyphenated["id"]]


def test_a_query_at_a_past_version_still_filters_by_text(project: Any) -> None:
    orders, _ = _apply(project, "Orders", "Invoices")
    version = project.store.knowledge_version

    found = project.knowledge.query("orders", at_version=version)

    assert [e["id"] for e in found] == [orders["id"]]


def test_stale_knowledge_is_hidden_unless_history_is_asked_for(project: Any) -> None:
    (orders,) = _apply(project, "Orders")
    _force(project, "entity", orders["id"], stale=True)

    assert project.knowledge.query("orders") == []
    assert [e["id"] for e in project.knowledge.query("orders", historical=True)] == [orders["id"]]


# --- approve_command ------------------------------------------------------------------------


def test_approving_a_command_is_recorded_as_the_local_human(project: Any) -> None:
    before = project.policy()
    command = contract()["verification"][0]["command"]

    policy = project.approve_command(command)

    assert _writers(project, "policy", policy) == ["local-human"]
    assert set(policy) == set(before) | {"version"}
    assert policy["allowed_commands"][-1] == command


# --- reconcile ------------------------------------------------------------------------------


def test_reconcile_without_changes_reports_nothing_and_keeps_the_knowledge_version(
    project: Any,
) -> None:
    project.reconcile()
    version = project.store.knowledge_version

    result = project.reconcile()

    assert project.store.knowledge_version == version
    assert result["changed_paths"] == []
    assert result["knowledge_version"] == version


# --- release --------------------------------------------------------------------------------


def _claimed(project: Any) -> tuple[str, str]:
    project.approve_command(contract()["verification"][0]["command"])
    task = project.create_task(contract())["id"]
    project.ready(task)
    session = project.join("worker", ["code", "terminal"])["session"]
    project.claim(task, session)
    return task, session


def test_releasing_without_a_blocker_returns_the_task_to_ready(project: Any) -> None:
    task, session = _claimed(project)
    (lease,) = [item for item in project.store.list("lease") if item["task_id"] == task]

    released = project.release(task, session)

    assert (released["state"], released["blocker"]) == ("READY", None)
    assert project.store.get(lease["id"], "lease")["state"] == "RELEASED"


# --- resume ---------------------------------------------------------------------------------


def test_resume_reports_the_workspace_and_whether_it_changed_since_the_checkpoint(
    project: Any,
) -> None:
    task, session = _claimed(project)
    project.checkpoint(task, session, checkpoint())

    unchanged = project.resume(task, session)
    (project.root / "app.py").write_text("value = 2\n", encoding="utf-8")
    changed = project.resume(task, session)

    assert unchanged["workspace"] == str(project.root)
    assert (unchanged["baseline_changed"], changed["baseline_changed"]) == (False, True)


def test_resume_passes_its_budget_to_the_context(project: Any) -> None:
    task, session = _claimed(project)
    project.checkpoint(task, session, checkpoint())

    # Too small for the mandatory context: resume must refuse it, not fall back to
    # its default budget.
    with pytest.raises(ControlError, match="never truncate it"):
        project.resume(task, session, budget=600)
    resumed = project.resume(task, session, budget=16000)
    expected = project.context(task, 16000)
    assert {key: resumed[key] for key in expected} == expected
