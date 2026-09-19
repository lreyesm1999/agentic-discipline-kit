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


# --- claim ----------------------------------------------------------------------------------


def _claim(project: Any, subject: str, authority: str, value: int) -> dict[str, Any]:
    return project.knowledge.claim(
        {
            "subject": subject,
            "predicate": "retention_days",
            "value": value,
            "source_ref": "brief.md",
            "authority": authority,
            "confidence": 1,
            "observation": "DECLARED",
        }
    )


def test_a_claim_repeating_the_canonical_value_is_no_conflict(project: Any) -> None:
    (orders,) = _apply(project, "Orders")
    canonical = _claim(project, orders["id"], "human", 30)

    repeated = _claim(project, orders["id"], "documentation", 30)

    assert project.store.get(canonical["id"], "claim")["disposition"] == "CANONICAL"
    assert (repeated["disposition"], repeated["conflicts"]) == ("CANDIDATE", [])


# --- lifecycle, context, invalidate ---------------------------------------------------------


def test_retiring_knowledge_records_the_reason_and_what_it_affects(project: Any) -> None:
    (orders,) = _apply(project, "Orders")

    result = project.knowledge.lifecycle(orders["id"], "RETIRED", "replaced by billing")

    assert project.store.get(orders["id"], "entity")["lifecycle_reason"] == "replaced by billing"
    assert result["affected"] == []


def test_a_directory_scope_with_a_trailing_slash_selects_its_code(project: Any) -> None:
    (project.root / "LibX").mkdir()
    (project.root / "LibX" / "a.py").write_text("value = 1\n", encoding="utf-8")
    project.reconcile()
    project.approve_command(contract()["verification"][0]["command"])
    task = project.create_task({**contract(), "scope": ["LibX/"]})["id"]

    sources = project.context(task)["sources"]

    assert [e["source_ref"] for e in sources if e["type"] == "file"] == ["LibX/a.py"]


def _first(project: Any, kind: str, data: dict[str, Any]) -> None:
    """Store a record whose id sorts before every generated one."""
    prefix = kind.upper()[:4]
    with project.store.transaction():
        project.store.put(kind, {**data, "id": f"{prefix}-!"})


def test_invalidation_reaches_tasks_and_claims_after_ones_it_skips(project: Any) -> None:
    from agentic_discipline.control.verification import invalidate, verify

    task, session = _claimed(project)
    verify(project, task, session)
    (orders,) = _apply(project, "Orders")
    canonical = _claim(project, orders["id"], "human", 30)
    _first(project, "task", {**project.store.get(task, "task")})
    _first(project, "claim", {**canonical, "disposition": "CANDIDATE"})
    (project.root / "app.py").write_text("value = 2\n", encoding="utf-8")
    _force(project, "entity", orders["id"], stale=True)

    result = invalidate(project)

    assert result["invalidated"]
    assert project.store.get(canonical["id"], "claim")["disposition"] == "STALE"


# --- workspaces, leases and transitions -----------------------------------------------------


def test_a_directory_scope_with_a_trailing_slash_overlaps_its_files() -> None:
    from agentic_discipline.control.workspaces import parallel_safety

    left = {"scope": ["LibX/a.py"], "boundaries": [], "risk": "LOW"}
    right = {"scope": ["LibX/"], "boundaries": [], "risk": "LOW"}

    assert parallel_safety(left, right)["status"] == "CONFLICTING"
    assert parallel_safety(right, left)["status"] == "CONFLICTING"


def test_ready_clears_a_leftover_active_run(project: Any) -> None:
    project.approve_command(contract()["verification"][0]["command"])
    task = project.create_task(contract())["id"]
    _force(project, "task", task, state="FAILED", active_run="RUN-left-over")

    assert project.ready(task)["active_run"] is None


def test_a_lease_of_one_second_is_accepted(project: Any) -> None:
    task, session = _claimed(project)

    lease = project.heartbeat(task, session, 1)

    assert lease["state"] == "ACTIVE"


def test_cancelling_a_task_is_recorded_as_the_local_owner(project: Any) -> None:
    project.approve_command(contract()["verification"][0]["command"])
    task = project.create_task(contract())["id"]

    cancelled = project.transition(task, "CANCELLED", "no longer needed")

    assert _writers(project, "task", cancelled) == ["local-owner"]


def test_a_symbol_retired_by_hand_stays_retired_when_its_file_changes(project: Any) -> None:
    (project.root / "lib.py").write_text("def total():\n    return 1\n", encoding="utf-8")
    project.reconcile()
    (symbol,) = [
        e
        for e in project.store.list("entity")
        if e.get("type") == "symbol" and e["name"] == "total"
    ]
    project.knowledge.lifecycle(symbol["id"], "RETIRED", "replaced by sums")

    (project.root / "lib.py").write_text("def total():\n    return 2\n", encoding="utf-8")
    project.reconcile()

    assert project.store.get(symbol["id"], "entity")["lifecycle"] == "RETIRED"


def test_a_claim_about_something_that_is_not_knowledge_is_refused(project: Any) -> None:
    project.approve_command(contract()["verification"][0]["command"])
    task = project.create_task(contract())["id"]

    with pytest.raises(ControlError) as caught:
        _claim(project, task, "human", 30)

    assert caught.value.code == "NOT_FOUND"


def test_context_reads_the_latest_evidence_of_the_task(project: Any) -> None:
    from agentic_discipline.control.verification import verify

    task, session = _claimed(project)
    verify(project, task, session)

    assert project.context(task)["mandatory"]["current_failures"] == []


# --- clocks and tokens ----------------------------------------------------------------------

NOW = 2_000_000_000.0


def _frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    import time

    monkeypatch.setattr(time, "time", lambda: NOW)


def _lease(project: Any, task: str) -> dict[str, Any]:
    (lease,) = [item for item in project.store.list("lease") if item["task_id"] == task]
    return lease


def _expire(project: Any) -> None:
    with project.store.transaction():
        project._expire()


def test_a_lease_expires_at_the_instant_it_ends(
    project: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    task, session = _claimed(project)
    _force(project, "lease", _lease(project, task)["id"], expires_at=NOW)
    _frozen(monkeypatch)

    with pytest.raises(ControlError) as caught:
        project.owned(task, session)
    _expire(project)

    assert caught.value.code == "LEASE_LOST"
    assert _lease(project, task)["state"] == "EXPIRED"
    assert project.store.get(task, "task")["state"] == "READY"


def test_a_running_verifier_keeps_its_lease_only_before_its_deadline(
    project: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    task, _ = _claimed(project)
    _force(project, "lease", _lease(project, task)["id"], expires_at=NOW - 1)
    _force(project, "task", task, active_run="RUN-1", active_run_deadline=NOW)
    _frozen(monkeypatch)

    _expire(project)

    assert _lease(project, task)["state"] == "EXPIRED"


def test_a_running_task_without_a_recorded_deadline_still_expires(
    project: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    task, _ = _claimed(project)
    _force(project, "lease", _lease(project, task)["id"], expires_at=NOW - 1)
    _force(project, "task", task, active_run="RUN-legacy")
    _frozen(monkeypatch)

    _expire(project)

    assert _lease(project, task)["state"] == "EXPIRED"


def test_a_session_token_carries_256_bits(project: Any) -> None:
    session = project.join("worker", ["code"])["session"]
    assert len(session) == 43


def test_adoption_stages_its_database_where_measurement_never_looks(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pathlib import Path

    from agentic_discipline.control.discovery import allowed
    from agentic_discipline.control.plane import adopt

    created: list[Path] = []
    real_mkdir = Path.mkdir

    def mkdir(self: Path, *args: Any, **kwargs: Any) -> None:
        created.append(self)
        real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", mkdir)
    (tmp_path / "app.py").write_text("value = 1\n", encoding="utf-8")

    adopt(tmp_path)

    # The staging directory is the one renamed into place, so it no longer exists.
    (staging,) = {p for p in created if p.parent.name == ".agentic" and not p.exists()}
    assert staging.name.startswith("adopt-")
    assert allowed(staging.relative_to(tmp_path) / "state.db") is False


# --- proof of dependencies ------------------------------------------------------------------


def test_a_dependency_without_proof_is_bound_as_having_none(project: Any) -> None:
    from agentic_discipline.control.verification import binding

    project.approve_command(contract()["verification"][0]["command"])
    first = project.create_task(contract())
    second = project.create_task({**contract(), "dependencies": [first["id"]]})

    assert binding(project, second)["dependencies"] == {first["id"]: []}


def test_a_completed_task_without_recorded_proof_is_not_proven(project: Any) -> None:
    from agentic_discipline.control.verification import proof_current

    project.approve_command(contract()["verification"][0]["command"])
    task = project.create_task(contract())
    forged = _force(project, "task", task["id"], state="COMPLETED")

    assert "proof" not in forged
    assert proof_current(project, forged) is False


# --- checks repeated behind an earlier one --------------------------------------------------


@pytest.mark.parametrize("field", ["state", "version", "id", "workspace_id", "integration"])
def test_server_owned_fields_are_refused_even_past_contract_validation(
    project: Any, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    # The contract validator already rejects these keys; this check stands behind it.
    import agentic_discipline.control.plane as plane_module

    monkeypatch.setattr(plane_module, "task_contract", lambda contract: None)
    with pytest.raises(ControlError) as caught:
        project.create_task({**contract(), field: "forged"})
    assert (caught.value.code, str(caught.value)) == (
        "INVALID_TASK",
        "Execution state is server-owned",
    )


def test_a_busy_task_is_refused_before_its_changes_are_checked(project: Any) -> None:
    from agentic_discipline.control.verification import verify

    task, session = _claimed(project)
    _force(project, "task", task, active_run="RUN-elsewhere")
    (project.root / "outside.py").write_text("x = 1\n", encoding="utf-8")

    with pytest.raises(ControlError) as caught:
        verify(project, task, session)
    assert (caught.value.code, str(caught.value)) == (
        "VERIFICATION_BUSY",
        "A verifier is already running",
    )


def test_a_claim_whose_predicate_is_blank_is_refused(project: Any) -> None:
    (orders,) = _apply(project, "Orders")
    with pytest.raises(ControlError) as caught:
        project.knowledge.claim(
            {
                "subject": orders["id"],
                "predicate": "   ",
                "value": 30,
                "source_ref": "brief.md",
                "authority": "human",
                "confidence": 1,
                "observation": "DECLARED",
            }
        )
    assert (caught.value.code, str(caught.value)) == (
        "INVALID_ENTITY",
        "name must be nonempty text",
    )
