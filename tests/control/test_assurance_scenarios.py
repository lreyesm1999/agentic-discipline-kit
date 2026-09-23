"""The twelve scenarios Agentic Discipline 2.1 has to demonstrate, end to end.

Every verdict here comes from a real process and persisted records; nothing is stubbed.
Each test is named after the scenario it settles, so a regression says which promise broke.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from assurance_support import (
    BUDGET,
    FAILS,
    PASSES,
    UNRUNNABLE,
    checkpoint,
    claimed,
    contract,
    policy_obligation,
    sources,
    spec,
)

from agentic_discipline.control.assurance import service
from agentic_discipline.control.assurance.resolver import obligations_for
from agentic_discipline.control.contracts import ControlError
from agentic_discipline.control.plane import Plane, adopt
from agentic_discipline.control.verification import complete


@pytest.fixture
def repository(tmp_path: Path) -> Any:
    sources(
        tmp_path,
        {
            "src/report.py": "value = 1\n",
            "src/other.py": "unrelated = True\n",
        },
    )
    adopt(tmp_path)
    with Plane(tmp_path) as plane:
        yield plane


def _report(plane: Any, task_id: str) -> dict[str, Any]:
    return service.status(plane, task_id)["tasks"][0]


def _finish(plane: Any, task_id: str, session: str) -> dict[str, Any]:
    plane.checkpoint(task_id, session, checkpoint())
    return complete(plane, task_id, session)


# --- 1 basic verification -------------------------------------------------------------


def test_scenario_1_a_task_compiles_obligations_runs_verifiers_and_completes(
    repository: Any,
) -> None:
    task_id, session = claimed(repository)
    plan = service.compile_plan(repository, task_id, phase="INITIAL")

    assert len(plan["obligations"]) == 1
    outcome = service.verify(repository, task_id, session)

    assert outcome["status"] == "PASS"
    assert outcome["decision"]["decision"] == "COMPLETE"
    assert [o["status"] for o in _report(repository, task_id)["obligations"]] == ["VERIFIED"]
    assert _report(repository, task_id)["proof_debt"] == 0
    assert _finish(repository, task_id, session)["state"] == "COMPLETED"


# --- 2 failed obligation --------------------------------------------------------------


def test_scenario_2_a_failing_verifier_blocks_completion(repository: Any) -> None:
    task_id, session = claimed(repository, contract(verification=[spec("unit", [0], FAILS)]))
    service.compile_plan(repository, task_id, phase="INITIAL")

    outcome = service.verify(repository, task_id, session)

    assert outcome["status"] == "FAIL"
    assert outcome["decision"]["decision"] == "REPAIR"
    assert [o["status"] for o in _report(repository, task_id)["obligations"]] == ["FAILED"]
    plane_task = repository.store.get(task_id, "task")
    assert plane_task["state"] == "FAILED"
    repository.checkpoint(task_id, session, checkpoint())
    with pytest.raises(ControlError) as caught:
        complete(repository, task_id, session)
    assert caught.value.code == "INVALID_TRANSITION"


# --- 3 stale evidence -----------------------------------------------------------------


def test_scenario_3_changing_proven_code_stops_the_obligation_being_verified(
    repository: Any,
) -> None:
    task_id, session = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    assert _report(repository, task_id)["counts"] == {"VERIFIED": 1}

    (repository.root / "src" / "report.py").write_text("value = 2\n", encoding="utf-8")

    report = _report(repository, task_id)
    assert report["counts"] == {"STALE": 1}
    assert report["proof_debt"] == 1
    assert report["decision"]["decision"] == "EXPAND_VERIFICATION"
    # Running the same verifier against the new source restores the claim.
    assert service.verify(repository, task_id, session)["status"] == "PASS"
    assert _report(repository, task_id)["counts"] == {"VERIFIED": 1}


# --- 4 unrelated change ---------------------------------------------------------------


def test_scenario_4_an_unrelated_edit_leaves_a_narrow_obligation_verified(
    repository: Any,
) -> None:
    """A policy obligation is bound to the paths that raised it, not to the whole scope."""
    task_id, session = claimed(
        repository,
        contract(
            acceptance=["Access rules hold"],
            verification=[spec("security", [0])],
            risk="STANDARD",
        ),
    )
    sources(repository.root, {"src/auth/login.py": "def login():\n    return True\n"})
    service.reconcile(repository, task_id)
    authorization = policy_obligation(repository, task_id, "SEC-AUTHZ")
    assert authorization["affected_paths"] == ["src/auth/login.py"]
    service.verify(repository, task_id, session)
    before = {o["id"]: o["status"] for o in _report(repository, task_id)["obligations"]}
    assert before[authorization["id"]] == "VERIFIED"

    (repository.root / "src" / "other.py").write_text("unrelated = False\n", encoding="utf-8")

    after = {o["id"]: o["status"] for o in _report(repository, task_id)["obligations"]}
    assert after[authorization["id"]] == "VERIFIED"
    # The task-wide acceptance obligation is bound to the whole declared scope, so it is
    # conservatively stale. The authorization claim is not, and needs no rerun.
    assert sorted(set(after.values())) == ["STALE", "VERIFIED"]


# --- 5 assurance expansion ------------------------------------------------------------


def test_scenario_5_a_diff_touching_an_undeclared_surface_adds_obligations(
    repository: Any,
) -> None:
    task_id, session = claimed(
        repository,
        contract(
            acceptance=["The report renders"],
            verification=[spec("unit", [0]), spec("security", [0])],
            risk="STANDARD",
        ),
    )
    initial = service.compile_plan(repository, task_id, phase="INITIAL")
    assert initial["signals"] == []
    assert len(initial["obligations"]) == 1

    sources(
        repository.root,
        {
            "src/auth/login.py": "def login():\n    return True\n",
            "src/migrations/0001.sql": "ALTER TABLE accounts ADD COLUMN tier TEXT;\n",
        },
    )
    reconciled = service.reconcile(repository, task_id)

    assert "auth" in reconciled["signals"] and "migration" in reconciled["signals"]
    policies = {p for o in obligations_for(repository, task_id) for p in o["origin"]["policy_ids"]}
    assert {"SEC-AUTHZ", "MIG-SAFE"} <= policies
    assert len(reconciled["expansion"]["added"]) >= 2
    view = service.plan_view(repository, task_id)
    assert view["expanded_by"] == sorted(reconciled["expansion"]["added"])
    assert _report(repository, task_id)["proof_debt"] >= 3
    del session


# --- 6 no silent contraction ----------------------------------------------------------


def test_scenario_6_recompiling_never_drops_or_weakens_a_recorded_obligation(
    repository: Any,
) -> None:
    task_id, _ = claimed(
        repository,
        contract(
            acceptance=["Access rules hold"],
            verification=[spec("security", [0])],
            risk="HIGH",
        ),
    )
    sources(repository.root, {"src/auth/login.py": "def login():\n    return True\n"})
    service.reconcile(repository, task_id)
    authorization = policy_obligation(repository, task_id, "SEC-AUTHZ")

    # The surface that raised it disappears from the diff; the obligation does not.
    (repository.root / "src" / "auth" / "login.py").unlink()
    again = service.reconcile(repository, task_id)

    assert authorization["id"] in again["retained"]
    kept = repository.store.get(authorization["id"], "obligation")
    assert (kept["mandatory"], kept["enforced"], kept["criticality"]) == (True, True, "HIGH")
    assert kept["status"] == "UNRESOLVED"


def test_scenario_6_a_weaker_recompiled_obligation_is_refused_and_recorded(
    repository: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An agent that recompiles a mandatory claim as optional does not get its way."""
    from agentic_discipline.control.assurance import compiler

    task_id, _ = claimed(repository, contract(risk="HIGH"))
    service.compile_plan(repository, task_id, phase="INITIAL")
    original = compiler.contract_obligations

    def weakened(task: dict[str, Any], registry: Any, phase: str) -> list[dict[str, Any]]:
        return [
            {**o, "mandatory": False, "criticality": "LOW", "acceptable_proof_capabilities": []}
            for o in original(task, registry, phase)
        ]

    monkeypatch.setattr(compiler, "contract_obligations", weakened)
    plan = service.reconcile(repository, task_id)

    assert plan["refused_contractions"]
    refused = plan["refused_contractions"][0]["refused"]
    assert "mandatory obligation would become optional" in refused
    assert "criticality would be lowered" in refused
    stored = repository.store.get(
        refused and plan["refused_contractions"][0]["obligation_id"], "obligation"
    )
    assert (stored["mandatory"], stored["criticality"]) == (True, "HIGH")
    events = [e for e in repository.store.timeline() if e["action"] == "assurance.compile"]
    assert events[0]["payload"]["refused_contractions"]


def test_scenario_6_only_an_audited_waiver_can_close_an_obligation_without_proof(
    repository: Any,
) -> None:
    task_id, _ = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    obligation = obligations_for(repository, task_id)[0]

    result = service.waive(repository, obligation["id"], "accepted for the spike", "owner")

    assert result["obligation"]["status"] == "WAIVED"
    assert result["waiver"]["reason"] == "accepted for the spike"
    assert result["waiver"]["authorization"] == "owner"
    assert _report(repository, task_id)["proof_debt"] == 0
    assert _report(repository, task_id)["counts"] == {"WAIVED": 1}
    assert [e["action"] for e in repository.store.timeline()].count("assurance.waive") == 1


def test_scenario_6_a_waiver_cannot_hide_a_current_failure(repository: Any) -> None:
    task_id, session = claimed(repository, contract(verification=[spec("unit", [0], FAILS)]))
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    obligation = obligations_for(repository, task_id)[0]

    with pytest.raises(ControlError) as caught:
        service.waive(repository, obligation["id"], "inconvenient", "owner")

    assert (caught.value.code, str(caught.value)) == (
        "EVIDENCE_REFUTES_CLAIM",
        "Current evidence refutes this claim; a waiver cannot hide it",
    )


# --- 7 conflicting evidence -----------------------------------------------------------


def test_scenario_7_a_pass_beside_a_fail_is_conflicted_and_blocks_completion(
    repository: Any,
) -> None:
    task_id, session = claimed(
        repository,
        contract(
            acceptance=["The reported value is one"],
            verification=[spec("acceptance", [0], PASSES), spec("property", [0], FAILS)],
        ),
    )
    service.compile_plan(repository, task_id, phase="INITIAL")

    outcome = service.verify(repository, task_id, session)

    assert _report(repository, task_id)["counts"] == {"CONFLICTED": 1}
    assert outcome["decision"]["decision"] == "BLOCK"
    assert outcome["status"] == "FAIL"
    explained = service.explain(repository, obligations_for(repository, task_id)[0]["id"])
    assert sorted(e["result"] for e in explained["evidence"]) == ["FAIL", "PASS"]
    assert explained["status"] == "CONFLICTED"


def test_scenario_7_execution_order_cannot_turn_a_conflict_into_a_pass(
    repository: Any,
) -> None:
    """The later run does not win; both current verdicts are read together."""
    task_id, session = claimed(
        repository,
        contract(
            acceptance=["The reported value is one"],
            verification=[spec("property", [0], FAILS), spec("acceptance", [0], PASSES)],
        ),
    )
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    assert _report(repository, task_id)["counts"] == {"CONFLICTED": 1}


# --- 8 deterministic dominance --------------------------------------------------------


def test_scenario_8_a_deterministic_route_is_chosen_over_agent_judgment(
    repository: Any,
) -> None:
    task_id, _ = claimed(
        repository,
        contract(
            acceptance=["The report renders"],
            verification=[
                spec("unit", [0]),
                spec("mutation", [0]),
                spec("adversarial", [0]),
            ],
            risk="HIGH",
        ),
    )
    service.compile_plan(repository, task_id, phase="INITIAL")
    strength = policy_obligation(repository, task_id, "TEST-STRENGTH")

    assert strength["plan"]["route"].startswith("mutation supplies")
    assert strength["plan"]["human_required"] is False
    task = repository.store.get(task_id, "task")
    chosen = {v["kind"] for v in task["verification"] if v["kind"] == "mutation"}
    assert chosen == {"mutation"}


def test_scenario_8_judgment_evidence_does_not_close_a_deterministically_reachable_claim(
    repository: Any,
) -> None:
    from agentic_discipline.control.assurance.resolver import resolve, task_evidence

    task_id, session = claimed(
        repository,
        contract(
            acceptance=["The report renders"],
            verification=[spec("unit", [0]), spec("mutation", [0])],
            risk="HIGH",
        ),
    )
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    strength = policy_obligation(repository, task_id, "TEST-STRENGTH")
    assert strength["plan"]["deterministic_available"]

    # Relabel the passing run as agent judgment, leaving everything else identical.
    task = repository.store.get(task_id, "task")
    for record in repository.store.list("evidence"):
        if strength["id"] in record["obligation_ids"]:
            with repository.store.transaction():
                repository.store.put(
                    "evidence",
                    {**record, "evidence_class": "AGENT_JUDGMENT"},
                    expected=record["version"],
                )

    evidence = task_evidence(repository, task["id"])
    assert resolve(repository, task, strength, evidence=evidence)["status"] == "UNRESOLVED"


def test_scenario_8_judgment_is_still_used_when_nothing_deterministic_is_declared(
    repository: Any,
) -> None:
    task_id, _ = claimed(
        repository,
        contract(
            acceptance=["The report renders"],
            verification=[spec("unit", [0]), spec("adversarial", [0])],
            risk="HIGH",
        ),
    )
    service.compile_plan(repository, task_id, phase="INITIAL")
    strength = policy_obligation(repository, task_id, "TEST-STRENGTH")

    assert strength["plan"]["route"].startswith("adversarial supplies falsification_review")
    assert strength["plan"]["deterministic_available"] == ["falsification", "test_strength"]


# --- 9 progressive escalation ---------------------------------------------------------


def test_scenario_9_a_route_that_reaches_no_verdict_escalates_to_a_deeper_one(
    repository: Any,
) -> None:
    task_id, session = claimed(
        repository,
        contract(
            acceptance=["The report renders"],
            verification=[
                spec("unit", [0]),
                spec("property", [], UNRUNNABLE),
                spec("mutation", []),
            ],
            risk="HIGH",
        ),
    )
    service.compile_plan(repository, task_id, phase="INITIAL")
    strength = policy_obligation(repository, task_id, "TEST-STRENGTH")
    assert strength["plan"]["route"].startswith("property supplies")
    assert strength["level"] == 2

    outcome = service.verify(repository, task_id, session)

    assert strength["id"] in outcome["escalated"]
    escalated = repository.store.get(strength["id"], "obligation")
    assert escalated["floor"] == 3
    assert escalated["plan"]["route"].startswith("mutation supplies")
    assert outcome["decision"]["decision"] == "COMPLETE"
    blocked = [e for e in repository.store.list("evidence") if e["result"] == "BLOCKED"]
    assert len(blocked) == 1 and blocked[0]["kind"] == "property"
    assert service.explain(repository, strength["id"])["status"] == "VERIFIED"


# --- 10 human required ----------------------------------------------------------------


def test_scenario_10_an_unautomatable_claim_produces_a_concrete_human_request(
    repository: Any,
) -> None:
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
    service.verify(repository, task_id, session)
    accepted = policy_obligation(repository, task_id, "HUMAN-ACCEPTANCE")

    explained = service.explain(repository, accepted["id"])

    assert explained["status"] == "HUMAN_REQUIRED"
    request = explained["human_request"]
    assert request["claim"] == accepted["claim"]
    assert request["inspect"] == ["src/report.py"]
    assert "src/report.py" in request["remaining_judgment"]
    assert request["automatic_checks_passed"] == ["mutation", "unit"]
    assert request["resolve_with"].startswith("agentic assurance resolve ")
    assert _report(repository, task_id)["decision"]["decision"] == "HUMAN_REQUIRED"

    recorded = service.resolve_human(
        repository, accepted["id"], "The code owner accepted this critical change"
    )

    assert recorded["evidence"]["evidence_class"] == "HUMAN"
    assert recorded["evidence"]["result"] == "PASS"
    assert service.explain(repository, accepted["id"])["status"] == "VERIFIED"
    assert _report(repository, task_id)["proof_debt"] == 0


def test_scenario_10_a_human_verdict_goes_stale_when_what_it_judged_changes(
    repository: Any,
) -> None:
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
    accepted = policy_obligation(repository, task_id, "HUMAN-ACCEPTANCE")
    service.resolve_human(repository, accepted["id"], "accepted by the code owner")
    assert service.explain(repository, accepted["id"])["status"] == "VERIFIED"

    (repository.root / "src" / "report.py").write_text("value = 2  # changed again\n")

    assert service.explain(repository, accepted["id"])["status"] == "STALE"


# --- 11 bounded repair ----------------------------------------------------------------


def test_scenario_11_a_repairable_failure_reverifies_only_what_it_affected(
    repository: Any,
) -> None:
    task_id, session = claimed(
        repository,
        contract(
            acceptance=["The report renders", "Access rules hold"],
            verification=[
                spec("unit", [0]),
                spec("security", [1], FAILS),
            ],
            risk="STANDARD",
        ),
    )
    service.compile_plan(repository, task_id, phase="INITIAL")
    first = service.verify(repository, task_id, session)

    assert first["decision"]["decision"] == "REPAIR"
    states = {o["claim"]: o["status"] for o in _report(repository, task_id)["obligations"]}
    assert states["The report renders"] == "VERIFIED"
    assert states["Access rules hold"] == "FAILED"

    # Repair: the security verifier now passes. Only its obligation needs a run.
    task = repository.store.get(task_id, "task")
    repaired = [
        {**v, "command": PASSES} if v["kind"] == "security" else v for v in task["verification"]
    ]
    repository.approve_command(PASSES)
    with repository.store.transaction():
        repository.store.put("task", {**task, "verification": repaired}, expected=task["version"])
    service.reconcile(repository, task_id)
    before = len(repository.store.list("evidence"))

    second = service.verify(repository, task_id, session)

    assert second["decision"]["decision"] == "COMPLETE"
    # Exactly the two verifiers whose obligations were open, not a full rerun of history.
    assert len(repository.store.list("evidence")) - before == 2


def test_scenario_11_a_failure_the_contract_no_longer_authorizes_blocks_instead(
    repository: Any,
) -> None:
    task_id, session = claimed(
        repository,
        contract(
            acceptance=["The report renders"],
            verification=[spec("unit", [0], FAILS)],
            budget={**BUDGET, "max_retries": 0},
        ),
    )
    service.compile_plan(repository, task_id, phase="INITIAL")

    outcome = service.verify(repository, task_id, session)

    assert outcome["decision"]["decision"] == "BLOCK"
    assert any("outside what this task may repair" in r for r in outcome["decision"]["reasons"])


@pytest.mark.parametrize(
    ("paths", "expected"),
    [(["src/report.py"], True), (["docs/guide.md"], False), (["policies/risk.md"], False)],
)
def test_scenario_11_repair_authority_stops_at_scope_and_protected_paths(
    repository: Any, paths: list[str], expected: bool
) -> None:
    """A failure reaching outside the declared scope, or into a protected contract, is not
    this task's to repair even while its retry budget is untouched."""
    from agentic_discipline.control.assurance.decision import repairable

    task_id, _ = claimed(repository, contract(scope=["src", "policies"]))
    service.compile_plan(repository, task_id, phase="INITIAL")
    obligation = obligations_for(repository, task_id)[0]
    with repository.store.transaction():
        repository.store.put(
            "obligation",
            {**obligation, "affected_paths": paths},
            expected=obligation["version"],
        )
    task = repository.store.get(task_id, "task")
    outstanding = [{"obligation_id": obligation["id"], "status": "FAILED"}]

    assert repairable(repository, task, outstanding) is expected


# --- 12 completion invariant ----------------------------------------------------------


@pytest.mark.parametrize("interface", ["service", "api", "cli", "mcp"])
def test_scenario_12_no_interface_completes_a_task_holding_mandatory_proof_debt(
    repository: Any, interface: str
) -> None:
    """Every surface reaches the same application layer, so one gate covers them all."""
    import json

    from agentic_discipline.control.api import call
    from agentic_discipline.control.mcp import Session

    task_id, session = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    repository.checkpoint(task_id, session, checkpoint())
    # The proven source changes after verification, so the claim is no longer supported.
    (repository.root / "src" / "report.py").write_text("value = 3\n", encoding="utf-8")
    assert _report(repository, task_id)["proof_debt"] == 1

    if interface == "service":
        with pytest.raises(ControlError) as caught:
            complete(repository, task_id, session)
        assert caught.value.code in {"PROOF_DEBT", "STALE_OR_FAILED_EVIDENCE"}
    elif interface == "api":
        with pytest.raises(ControlError) as caught:
            call(repository, "complete_task", {"task_id": task_id, "session": session}, local=True)
        assert caught.value.code in {"PROOF_DEBT", "STALE_OR_FAILED_EVIDENCE"}
    elif interface == "cli":
        from agentic_discipline.control.cli import main, parser

        with pytest.raises(SystemExit) as exited:
            main_args = ["--root", str(repository.root), "task", "complete", task_id]
            del main_args
            raise_on_cli(repository, task_id, session, main, parser)
        assert exited.value.code == 2
    else:
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
        answer = conversation.receive(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "complete_task",
                    "arguments": {"task_id": task_id, "session": session},
                },
            }
        )
        assert answer is not None and answer["result"]["isError"] is True
        body = json.loads(answer["result"]["content"][0]["text"])
        assert body["code"] in {"PROOF_DEBT", "STALE_OR_FAILED_EVIDENCE"}
    assert repository.store.get(task_id, "task")["state"] != "COMPLETED"


def raise_on_cli(plane: Any, task_id: str, session: str, main: Any, parser: Any) -> None:
    """Drive the real CLI entry point with a session file outside the repository."""
    import sys
    from unittest import mock

    directory = Path(plane.directory).parent.parent.parent / "sessions"
    directory.mkdir(exist_ok=True)
    path = directory / f"{task_id}.json"
    path.write_text(f'{{"session": "{session}"}}', encoding="utf-8")
    argv = [
        "agentic",
        "--root",
        str(plane.root),
        "task",
        "complete",
        task_id,
        "--session-file",
        str(path),
        "--json",
    ]
    with mock.patch.object(sys, "argv", argv):
        main()


# --- reference comparison, as one strategy among the others ------------------------------


def test_a_reference_comparison_is_just_another_verifier_with_what_it_compared_recorded(
    repository: Any,
) -> None:
    """A golden-file comparison is a deterministic verifier. The engine records what it
    compared, because both the reference and the candidate sit inside the claim's binding."""
    sources(
        repository.root,
        {
            "reference/onboarding.json": '{"steps": ["welcome", "verify", "done"]}\n',
            "src/onboarding.json": '{"steps": ["welcome", "verify", "done"]}\n',
        },
    )
    compare = [
        sys.executable,
        "-c",
        "import json,pathlib,sys;"
        "a=pathlib.Path('reference/onboarding.json').read_text();"
        "b=pathlib.Path('src/onboarding.json').read_text();"
        "sys.exit(0 if json.loads(a)==json.loads(b) else 1)",
    ]
    task_id, session = claimed(
        repository,
        contract(
            scope=["src", "reference"],
            acceptance=["The generated onboarding matches the approved reference"],
            verification=[
                {
                    "kind": "reference",
                    "command": compare,
                    "acceptance": [0],
                    "inputs": ["reference/onboarding.json", "src/onboarding.json"],
                }
            ],
        ),
    )
    service.compile_plan(repository, task_id, phase="INITIAL")

    outcome = service.verify(repository, task_id, session)

    assert outcome["decision"]["decision"] == "COMPLETE"
    (record,) = repository.store.list("evidence")
    assert record["evidence_class"] == "DETERMINISTIC"
    assert "judgment" not in record
    obligation = obligations_for(repository, task_id)[0]
    compared = record["obligation_bindings"][obligation["id"]]["files"]
    assert {"reference/onboarding.json", "src/onboarding.json"} <= set(compared)

    # Changing the candidate alone invalidates the comparison and then refutes it.
    (repository.root / "src" / "onboarding.json").write_text(
        '{"steps": ["welcome", "done"]}\n', encoding="utf-8"
    )

    assert service.explain(repository, obligation["id"])["status"] == "STALE"
    assert service.verify(repository, task_id, session)["decision"]["decision"] == "REPAIR"
    assert service.explain(repository, obligation["id"])["status"] == "FAILED"


def test_a_qualitative_reference_review_never_outranks_a_deterministic_comparison(
    repository: Any,
) -> None:
    """Where a comparator exists, a reviewer's opinion is not a substitute for it."""
    known = service.registry_for(repository)
    assert known.get("reference")["evidence_class"] == "DETERMINISTIC"
    assert known.get("reference-review")["evidence_class"] == "AGENT_JUDGMENT"
    assert "reference_comparison" in known.deterministic_capabilities()
    # The qualitative capability is deliberately a different one, so a reviewer cannot be
    # selected for a claim a comparator can settle.
    assert "qualitative_reference_comparison" not in known.deterministic_capabilities()
    assert known.capabilities("reference") & known.capabilities("reference-review") == set()
