"""CLI, API, MCP and console over one assurance service, and the 2.0 to 2.1 migration.

The point of these cases is that no surface has its own idea of the assurance state, and
that a 2.0 project keeps working until an owner upgrades it on purpose.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from assurance_support import FAILS, checkpoint, claimed, contract, planned, sources, spec

from agentic_discipline.control.api import LOCAL_ONLY, READ_ONLY, SCHEMAS, call
from agentic_discipline.control.assurance import migration, service
from agentic_discipline.control.assurance.resolver import obligations_for
from agentic_discipline.control.cli import main, render_assurance
from agentic_discipline.control.contracts import ControlError
from agentic_discipline.control.mcp import Session
from agentic_discipline.control.plane import Plane, adopt
from agentic_discipline.control.verification import complete

ASSURANCE_OPERATIONS = {name for name in SCHEMAS if name.startswith("assurance_")}


@pytest.fixture
def repository(tmp_path: Path) -> Any:
    sources(tmp_path, {"src/report.py": "value = 1\n"})
    adopt(tmp_path)
    with Plane(tmp_path) as plane:
        yield plane


def _cli(plane: Any, *arguments: str) -> tuple[int, str]:
    argv = ["agentic", "--root", str(plane.root), "assurance", *arguments]
    with mock.patch.object(sys, "argv", argv):
        try:
            main()
        except SystemExit as exit_code:
            return int(exit_code.code or 0), ""
    return 0, ""


def _session_file(plane: Any, session: str) -> Path:
    path = Path(plane.root).parent / "worker-session.json"
    path.write_text(json.dumps({"session": session}), encoding="utf-8")
    return path


# --- one service behind every surface -------------------------------------------------


def test_every_assurance_operation_is_read_only_or_owner_only() -> None:
    assert ASSURANCE_OPERATIONS - READ_ONLY - LOCAL_ONLY == {"assurance_verify"}
    assert not READ_ONLY & LOCAL_ONLY


def test_a_worker_cannot_reach_the_owner_side_of_assurance(repository: Any) -> None:
    for name in sorted(ASSURANCE_OPERATIONS & LOCAL_ONLY):
        with pytest.raises(ControlError) as caught:
            call(repository, name, {}, local=False)
        assert caught.value.code == "PERMISSION_DENIED"


def test_mcp_offers_the_read_and_verify_tools_and_hides_the_owner_ones() -> None:
    offered = {name for name in SCHEMAS if name.startswith("assurance_") and name not in LOCAL_ONLY}
    assert offered == {
        "assurance_status",
        "assurance_plan",
        "assurance_explain",
        "assurance_debt",
        "assurance_registry",
        "assurance_integrity",
        "assurance_verify",
    }


def _initialized(repository: Any) -> Session:
    conversation = Session(repository)
    conversation.receive(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "t"},
            },
        }
    )
    conversation.receive({"jsonrpc": "2.0", "method": "notifications/initialized"})
    return conversation


def test_the_same_assurance_state_is_returned_through_the_api_mcp_and_console(
    repository: Any,
) -> None:
    task_id, session = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)

    from_api = call(repository, "assurance_status", {}, local=True)
    conversation = _initialized(repository)
    answer = conversation.receive(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "assurance_status", "arguments": {}},
        }
    )
    assert answer is not None
    from_mcp = answer["result"]["structuredContent"]
    from_console = call(repository, "assurance_status", {})

    assert from_api == from_mcp == from_console
    assert from_api["data"]["totals"]["proof_debt"] == 0


def test_an_owner_tool_is_not_offered_over_mcp_even_when_asked_for(repository: Any) -> None:
    conversation = _initialized(repository)
    tools = conversation.receive({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert tools is not None
    names = {tool["name"] for tool in tools["result"]["tools"]}
    assert "assurance_waive" not in names
    assert "assurance_status" in names

    refused = conversation.receive(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "assurance_waive",
                "arguments": {"obligation_id": "PO-1", "reason": "x", "authorization": "y"},
            },
        }
    )
    assert refused is not None
    assert refused["error"]["message"] == "Unknown tool or invalid arguments"


def test_the_read_only_tools_are_annotated_as_read_only(repository: Any) -> None:
    conversation = _initialized(repository)
    tools = conversation.receive({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert tools is not None
    annotations = {
        tool["name"]: tool["annotations"]["readOnlyHint"] for tool in tools["result"]["tools"]
    }
    assert annotations["assurance_status"] is True
    assert annotations["assurance_verify"] is False


def test_the_console_serves_the_assurance_view_and_nothing_mutating(repository: Any) -> None:
    from agentic_discipline.control.console import HTML, JS, handler

    task_id, session = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)

    assert "/api/assurance" in JS
    assert 'id="assuranceRows"' in HTML and 'id="obligationRows"' in HTML
    routes = handler(repository.root)
    assert not hasattr(routes, "do_POST")
    payload = call(repository, "assurance_status", {})["data"]
    assert payload["tasks"][0]["obligations"][0]["status"] == "VERIFIED"


# --- the CLI ---------------------------------------------------------------------------


def test_the_cli_reaches_every_assurance_action(repository: Any) -> None:
    task_id, session = claimed(repository)
    assert _cli(repository, "plan", task_id, "--compile")[0] == 0
    assert _cli(repository, "plan", task_id)[0] == 0
    assert _cli(repository, "registry", "--json")[0] == 0
    assert _cli(repository, "integrity")[0] == 0
    assert _cli(repository, "status")[0] == 0
    assert _cli(repository, "debt")[0] == 0
    path = _session_file(repository, session)
    assert _cli(repository, "verify", task_id, "--session-file", str(path))[0] == 0
    obligation = obligations_for(repository, task_id)[0]["id"]
    assert _cli(repository, "explain", obligation)[0] == 0


def test_a_failing_assurance_verify_exits_nonzero_from_the_cli(repository: Any) -> None:
    task_id, session = claimed(repository, contract(verification=[spec("unit", [0], FAILS)]))
    service.compile_plan(repository, task_id, phase="INITIAL")
    path = _session_file(repository, session)
    assert _cli(repository, "verify", task_id, "--session-file", str(path))[0] == 1


def test_a_waiver_from_the_cli_needs_both_a_reason_and_its_authority(
    repository: Any,
) -> None:
    task_id, _ = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    obligation = obligations_for(repository, task_id)[0]["id"]

    assert _cli(repository, "waive", obligation, "--reason", "spike")[0] == 2
    assert (
        _cli(repository, "waive", obligation, "--reason", "spike", "--authorization", "owner")[0]
        == 0
    )
    assert repository.store.get(obligation, "obligation")["status"] == "WAIVED"


def test_a_human_resolution_from_the_cli_needs_a_decision(repository: Any) -> None:
    task_id, session = claimed(
        repository,
        contract(
            acceptance=["The report renders"],
            verification=[spec("unit", [0]), spec("mutation", [])],
            risk="CRITICAL",
        ),
    )
    (repository.root / "src" / "report.py").write_text("value = 1  # revised\n")
    service.reconcile(repository, task_id)
    accepted = next(
        o
        for o in obligations_for(repository, task_id)
        if "HUMAN-ACCEPTANCE" in o["origin"]["policy_ids"]
    )

    assert _cli(repository, "resolve", accepted["id"])[0] == 2
    assert _cli(repository, "resolve", accepted["id"], "--decision", "accepted")[0] == 0
    assert service.explain(repository, accepted["id"])["status"] == "VERIFIED"
    del session


def test_a_rejected_human_verdict_is_recorded_as_a_refusal(repository: Any) -> None:
    task_id, _ = claimed(
        repository,
        contract(
            acceptance=["The report renders"],
            verification=[spec("unit", [0]), spec("mutation", [])],
            risk="CRITICAL",
        ),
    )
    (repository.root / "src" / "report.py").write_text("value = 1  # revised\n")
    service.reconcile(repository, task_id)
    accepted = next(
        o
        for o in obligations_for(repository, task_id)
        if "HUMAN-ACCEPTANCE" in o["origin"]["policy_ids"]
    )

    result = service.resolve_human(repository, accepted["id"], "not acceptable", accepted=False)

    assert result["evidence"]["result"] == "FAIL"
    assert result["evidence"]["judgment"] == "REJECTED"
    assert service.explain(repository, accepted["id"])["status"] == "FAILED"


def test_resolving_a_claim_that_has_an_automated_route_is_refused(repository: Any) -> None:
    task_id, _ = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    obligation = obligations_for(repository, task_id)[0]

    with pytest.raises(ControlError) as caught:
        service.resolve_human(repository, obligation["id"], "looks fine to me")

    assert (caught.value.code, str(caught.value)) == (
        "NOT_HUMAN_REQUIRED",
        "This obligation has an automated route; run it instead",
    )


def test_the_plain_reading_of_a_status_names_the_counts_the_debt_and_the_decision() -> None:
    text = render_assurance(
        "status",
        {
            "tasks": [
                {
                    "task_id": "TASK-104",
                    "required": 12,
                    "counts": {"VERIFIED": 9, "FAILED": 1, "UNKNOWN": 1, "HUMAN_REQUIRED": 1},
                    "proof_debt": 3,
                    "decision": {"decision": "BLOCK"},
                }
            ]
        },
    )
    assert "TASK-104 ASSURANCE" in text
    assert "Required obligations 12" in text
    assert "VERIFIED               9" in text
    assert "HUMAN_REQUIRED         1" in text
    assert "Proof debt           3" in text
    assert "Decision             BLOCK" in text


def test_the_plain_reading_of_an_explanation_shows_its_provenance_and_evidence() -> None:
    text = render_assurance(
        "explain",
        {
            "obligation": {"id": "PO-007"},
            "claim": "Historical profit calculations remain stable.",
            "required_because": "changed code affects a financial invariant",
            "affected_paths": ["src/profit/calculator.py"],
            "status": "CONFLICTED",
            "reason": "current evidence both supports and refutes this claim",
            "evidence": [
                {
                    "id": "EV-118",
                    "kind": "regression",
                    "result": "PASS",
                    "evidence_class": "DETERMINISTIC",
                    "currency": "CURRENT",
                },
                {
                    "id": "EV-124",
                    "kind": "property",
                    "result": "FAIL",
                    "evidence_class": "DETERMINISTIC",
                    "currency": "CURRENT",
                },
            ],
            "human_request": None,
        },
    )
    assert text.splitlines()[0] == "PO-007"
    assert "  Historical profit calculations remain stable." in text
    assert "  changed code affects a financial invariant" in text
    assert "  src/profit/calculator.py" in text
    assert "  EV-118 PASS CURRENT (regression, DETERMINISTIC)" in text
    assert "  CONFLICTED - current evidence both supports and refutes this claim" in text


def test_an_empty_assurance_reading_says_so_rather_than_printing_nothing() -> None:
    assert render_assurance("status", {"tasks": []}) == "No assurance plan has been compiled yet"


def test_reading_a_plan_before_one_exists_is_refused_with_what_to_do(
    repository: Any,
) -> None:
    task_id = planned(repository)
    with pytest.raises(ControlError) as caught:
        service.plan_view(repository, task_id)
    assert (caught.value.code, str(caught.value)) == (
        "NO_ASSURANCE_PLAN",
        "Compile an assurance plan for this task first",
    )


# --- migration -------------------------------------------------------------------------


def _two_point_zero(plane: Any) -> None:
    """Put the project back on the 2.0 schema, as an upgraded installation would find it."""
    with plane.store.transaction():
        plane.store.db.execute("UPDATE meta SET value='1' WHERE key='schema_version'")
    plane.store.schema_version = 1


def test_a_two_point_zero_project_keeps_working_until_it_is_migrated(
    repository: Any,
) -> None:
    task_id, session = claimed(repository)
    _two_point_zero(repository)

    assert service.enabled(repository) is False
    with pytest.raises(ControlError) as caught:
        service.status(repository, task_id)
    assert caught.value.code == "ASSURANCE_DISABLED"
    assert "agentic assurance migrate" in str(caught.value)

    # 2.0 completion is untouched: no obligations exist, so nothing new can block it.
    from agentic_discipline.control.verification import verify as run

    run(repository, task_id, session)
    repository.checkpoint(task_id, session, checkpoint())
    assert complete(repository, task_id, session)["state"] == "COMPLETED"
    assert repository.store.list("obligation") == []


def test_the_migration_says_what_it_will_do_before_doing_it(repository: Any) -> None:
    claimed(repository)
    _two_point_zero(repository)

    report = migration.migrate(repository, dry_run=True)

    assert report["dry_run"] is True
    assert (report["from_schema"], report["to_schema"]) == ("1", "2")
    assert report["acceptance_criteria"] == 1
    assert report["already_migrated"] is False
    assert any("mandatory proof obligation" in line for line in report["becomes"])
    assert report["unreconstructible"]
    assert repository.store.list("obligation") == []
    assert repository.store.schema_version == 1


def test_migrating_derives_obligations_and_keeps_legacy_evidence_provenance(
    repository: Any,
) -> None:
    task_id, session = claimed(repository)
    from agentic_discipline.control.verification import verify as run

    run(repository, task_id, session)
    _two_point_zero(repository)

    report = migration.migrate(repository)

    assert report["migrated"] is True
    assert report["obligations"] == 1
    assert report["reclassified_evidence"] == 1
    assert repository.store.schema_version == 2
    legacy = repository.store.list("evidence")[0]
    assert legacy["assurance_provenance"] == "LEGACY"
    assert legacy["evidence_class"] == "DETERMINISTIC"
    # The acceptance criterion it was recorded against is the one link that is real.
    assert legacy["obligation_ids"] == []
    assert service.status(repository, task_id)["tasks"][0]["counts"] == {"VERIFIED": 1}


def test_migrating_twice_changes_nothing_the_second_time(repository: Any) -> None:
    task_id, _ = claimed(repository)
    _two_point_zero(repository)
    first = migration.migrate(repository)

    second = migration.migrate(repository)

    assert second["obligations"] == first["obligations"]
    assert second["reclassified_evidence"] == 0
    assert len(obligations_for(repository, task_id)) == 1
    assert repository.store.audit()["status"] == "PASS"


def test_rolling_the_migration_back_returns_to_two_point_zero_and_keeps_the_records(
    repository: Any,
) -> None:
    task_id, _ = claimed(repository)
    _two_point_zero(repository)
    applied = migration.migrate(repository)

    result = migration.rollback(repository, applied["migration_id"], "reverting the upgrade")

    assert result["rolled_back"] is True
    assert result["obligations_retired"] == 1
    assert repository.store.schema_version == 1
    assert service.enabled(repository) is False
    # The records are kept for audit and no longer govern anything.
    assert len(repository.store.list("obligation")) == 1
    assert obligations_for(repository, task_id) == []
    assert repository.store.get(applied["migration_id"], "assurance_migration")["status"] == (
        "ROLLED_BACK"
    )


def test_migrating_again_after_a_rollback_reactivates_rather_than_duplicates(
    repository: Any,
) -> None:
    task_id, _ = claimed(repository)
    _two_point_zero(repository)
    applied = migration.migrate(repository)
    migration.rollback(repository, applied["migration_id"], "reverting")

    again = migration.migrate(repository)

    assert again["migrated"] is True
    assert len(repository.store.list("obligation")) == 1
    assert len(obligations_for(repository, task_id)) == 1
    assert repository.store.schema_version == 2


@pytest.mark.parametrize("reason", ["", "   "])
def test_a_rollback_without_a_reason_is_refused(repository: Any, reason: str) -> None:
    claimed(repository)
    _two_point_zero(repository)
    applied = migration.migrate(repository)

    with pytest.raises(ControlError) as caught:
        migration.rollback(repository, applied["migration_id"], reason)

    assert (caught.value.code, str(caught.value)) == (
        "REASON_REQUIRED",
        "Rollback requires a reason",
    )


def test_rolling_the_same_migration_back_twice_is_refused(repository: Any) -> None:
    claimed(repository)
    _two_point_zero(repository)
    applied = migration.migrate(repository)
    migration.rollback(repository, applied["migration_id"], "reverting")

    with pytest.raises(ControlError) as caught:
        migration.rollback(repository, applied["migration_id"], "again")

    assert (caught.value.code, str(caught.value)) == (
        "INVALID_MIGRATION",
        "Migration is not applied",
    )


def test_a_migrated_project_records_a_forecast_rather_than_a_retroactive_requirement(
    repository: Any,
) -> None:
    """The upgrade does not invent enforcement for a surface no diff ever confirmed."""
    task_id, _ = claimed(repository, contract(scope=["src", "auth"]))
    _two_point_zero(repository)

    migration.migrate(repository)

    forecast = next(o for o in obligations_for(repository, task_id) if o["derivation"] == "POLICY")
    assert (forecast["phase"], forecast["enforced"]) == ("INITIAL", False)
    assert service.status(repository, task_id)["tasks"][0]["required"] == 1


# --- the shipped example -----------------------------------------------------------------


def test_the_shipped_assurance_example_routes_every_claim_its_change_raises(
    repository: Any,
) -> None:
    """The example in `examples/control/` has to be one a project can actually run, and the
    routes its README promises have to be the ones the planner picks."""
    # The mutation gate runs this suite from a copy of the tree under `mutants/`, which
    # holds the package and the tests but not the examples, so the file is looked for in
    # each ancestor rather than at a fixed distance from this one.
    example = Path("examples/control/assurance-task.json")
    found = next(
        (
            parent / example
            for parent in Path(__file__).resolve().parents
            if (parent / example).is_file()
        ),
        None,
    )
    assert found is not None, f"{example} is missing"
    data = json.loads(found.read_text(encoding="utf-8"))
    for verifier in data["verification"]:
        repository.approve_command(verifier["command"])
    task = repository.create_task(data)
    repository.ready(task["id"])
    session = repository.join("example-worker", ["code"])["session"]
    repository.claim(task["id"], session)

    sources(
        repository.root,
        {
            "src/pnl/calculator.py": "def total(rows):\n    return sum(rows)\n",
            "src/api/reporting.py": "def report():\n    return {}\n",
            "migrations/0002_add_tier.sql": "ALTER TABLE accounts ADD COLUMN tier TEXT;\n",
        },
    )
    service.reconcile(repository, task["id"])

    routed = obligations_for(repository, task["id"])
    routes = {
        (o["origin"]["policy_ids"] or [f"acceptance:{o['origin']['acceptance_ids'][0]}"])[0]: o[
            "plan"
        ]["route"]
        for o in routed
    }

    assert routes["acceptance:0"].startswith("verifiers the task contract bound")
    assert routes["FIN-STABLE"].startswith("regression supplies historical_stability")
    assert routes["API-COMPAT"].startswith("contract supplies contract_compatibility")
    assert routes["MIG-SAFE"].startswith("migration supplies ")
    assert routes["TEST-STRENGTH"].startswith("property supplies falsification")
    # Every claim this change raises has a route; none is left unsatisfiable.
    assert all(not o["plan"]["unsatisfiable"] for o in routed)
    assert service.status(repository, task["id"])["tasks"][0]["required"] == 6


# --- explaining a whole task -------------------------------------------------------------


def test_explain_answers_for_a_task_as_well_as_for_one_claim(repository: Any) -> None:
    """The question people actually ask is why a task cannot finish."""
    task_id, session = claimed(
        repository,
        contract(
            acceptance=["The report renders", "Access rules hold"],
            verification=[spec("unit", [0]), spec("security", [1], FAILS)],
            risk="STANDARD",
        ),
    )
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)

    explained = service.explain(repository, task_id)

    assert explained["headline"] == f"{task_id} cannot complete."
    assert explained["can_complete"] is False
    assert explained["required"] == 2
    assert explained["counts"] == {"FAILED": 1, "VERIFIED": 1}
    assert explained["proof_debt"] == 1
    assert explained["decision"] == "REPAIR"
    (open_claim,) = explained["outstanding"]
    assert open_claim["claim"] == "Access rules hold"
    assert open_claim["status"] == "FAILED"
    assert open_claim["current_evidence"]
    assert explained["required_next_actions"] == [
        f"Resolve the failure behind {open_claim['obligation_id']}."
    ]


def test_explaining_a_task_whose_claims_are_all_resolved_says_it_can_complete(
    repository: Any,
) -> None:
    task_id, session = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)

    explained = service.explain(repository, task_id)

    assert explained["headline"] == f"{task_id} is ready to complete."
    assert (explained["can_complete"], explained["proof_debt"]) == (True, 0)
    assert explained["outstanding"] == []
    assert explained["required_next_actions"] == []


def test_explaining_a_task_with_no_plan_is_refused_with_what_to_do(repository: Any) -> None:
    task_id = planned(repository)
    with pytest.raises(ControlError) as caught:
        service.explain(repository, task_id)
    assert (caught.value.code, str(caught.value)) == (
        "NO_ASSURANCE_PLAN",
        "Compile an assurance plan for this task first",
    )


def test_the_plain_reading_of_a_task_explanation_names_the_open_claims_and_next_actions() -> None:
    text = render_assurance(
        "explain",
        {
            "headline": "TASK-104 cannot complete.",
            "required": 12,
            "counts": {"VERIFIED": 10, "FAILED": 1, "STALE": 1},
            "proof_debt": 2,
            "decision": "BLOCK",
            "outstanding": [
                {
                    "obligation_id": "PO-007",
                    "status": "FAILED",
                    "claim": "Historical profitability results remain stable.",
                    "criticality": "CRITICAL",
                    "reason": "current evidence refutes this claim",
                    "current_evidence": ["EVD-223"],
                    "stale_evidence": [],
                    "missing_verifiers": [],
                    "origin": "observed money surface in src/pnl/calculator.py",
                },
                {
                    "obligation_id": "PO-011",
                    "status": "STALE",
                    "claim": "The published interface stays compatible for existing callers.",
                    "criticality": "HIGH",
                    "reason": "the evidence for this claim no longer matches current inputs",
                    "current_evidence": [],
                    "stale_evidence": ["EVD-118"],
                    "missing_verifiers": [],
                    "origin": "observed public_api surface in src/api/reporting.py",
                },
            ],
            "required_next_actions": [
                "Resolve the failure behind PO-007.",
                "Run the verifier for PO-011 and record evidence.",
            ],
        },
    )

    assert text.splitlines()[0] == "TASK-104 cannot complete."
    assert "12 mandatory proof obligations." in text
    assert "  VERIFIED         10" in text
    assert "FAILED:" in text and "  PO-007" in text
    assert "STALE:" in text and "  PO-011" in text
    assert "  Evidence: EVD-223" in text
    assert "  1. Resolve the failure behind PO-007." in text
    assert "  2. Run the verifier for PO-011 and record evidence." in text


def test_the_cli_reaches_the_migration_and_its_rollback(repository: Any) -> None:
    claimed(repository)
    assert _cli(repository, "migrate", "--dry-run", "--json")[0] == 0

    assert _cli(repository, "migrate", "--json")[0] == 0
    applied = repository.store.list("assurance_migration")[-1]
    assert applied["status"] == "APPLIED"

    assert _cli(repository, "rollback", applied["id"])[0] == 2
    assert _cli(repository, "rollback", applied["id"], "--reason", "reverting")[0] == 0
    assert repository.store.get(applied["id"], "assurance_migration")["status"] == "ROLLED_BACK"


def test_the_plain_reading_of_a_human_required_claim_says_how_to_settle_it() -> None:
    text = render_assurance(
        "explain",
        {
            "obligation": {"id": "PO-017"},
            "claim": "A human explicitly accepted this critical change.",
            "required_because": "CRITICAL risk requires a recorded human acceptance of src/pnl",
            "affected_paths": [],
            "status": "HUMAN_REQUIRED",
            "reason": "no automated verifier can settle this claim",
            "evidence": [],
            "human_request": {
                "resolve_with": "agentic assurance resolve PO-017 --decision <text>",
            },
        },
    )

    assert "  (declared task scope)" in text
    assert "  none recorded" in text
    assert "Human resolution:" in text
    assert "  agentic assurance resolve PO-017 --decision <text>" in text


def test_a_declared_assurance_operation_without_a_handler_is_refused(
    repository: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The dispatch has no fall-through that quietly returns nothing."""
    from agentic_discipline.control.api import schema

    monkeypatch.setitem(SCHEMAS, "assurance_future", schema({}))
    with pytest.raises(ControlError) as caught:
        call(repository, "assurance_future", {}, local=True)
    assert (caught.value.code, str(caught.value)) == ("UNKNOWN_OPERATION", "assurance_future")


def test_a_task_explanation_with_nothing_open_prints_no_next_actions() -> None:
    text = render_assurance(
        "explain",
        {
            "headline": "TASK-1 is ready to complete.",
            "required": 1,
            "counts": {"VERIFIED": 1},
            "proof_debt": 0,
            "decision": "COMPLETE",
            "outstanding": [],
            "required_next_actions": [],
        },
    )
    assert text.splitlines() == [
        "TASK-1 is ready to complete.",
        "1 mandatory proof obligations.",
        "  VERIFIED         1",
    ]
    assert "Required next actions" not in text
