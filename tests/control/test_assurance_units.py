"""Unit behaviour of the assurance parts: model, compiler, registry, planner, resolver.

The scenario suite proves the engine end to end. These cases pin the pieces, so a change
that still produces a passing scenario but reasons differently is not silent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from assurance_support import (
    PASSES,
    claimed,
    contract,
    planned,
    policy_obligation,
    sources,
    spec,
)

from agentic_discipline.control.assurance import (
    compiler,
    model,
    planner,
    registry,
    resolver,
    service,
)
from agentic_discipline.control.contracts import ControlError
from agentic_discipline.control.plane import Plane, adopt


@pytest.fixture
def repository(tmp_path: Path) -> Any:
    sources(tmp_path, {"src/report.py": "value = 1\n", "src/other.py": "unrelated = True\n"})
    adopt(tmp_path)
    with Plane(tmp_path) as plane:
        yield plane


# --- model ----------------------------------------------------------------------------


def _obligation(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "task_id": "TASK-1",
        "claim": "The value is one",
        "origin": {
            "requirement_ids": [],
            "acceptance_ids": [0],
            "policy_ids": [],
            "architecture_ids": [],
            "generated_reason": "acceptance criterion",
        },
        "derivation": "CONTRACT",
        "criticality": "STANDARD",
        "mandatory": True,
        "status": "UNRESOLVED",
        "phase": "INITIAL",
        "enforced": True,
        "acceptable_proof_capabilities": ["unit"],
        "required_verifiers": ["digest-a"],
        "affected_paths": ["src"],
        "affected_symbols": [],
        "dependencies": [],
    }
    base.update(overrides)
    return base


def test_obligation_identity_is_derived_from_the_task_and_its_origin() -> None:
    first = model.obligation_id("TASK-1", "acceptance:0")
    assert first == model.obligation_id("TASK-1", "acceptance:0")
    assert first != model.obligation_id("TASK-1", "acceptance:1")
    assert first != model.obligation_id("TASK-2", "acceptance:0")
    assert first.startswith("PO-") and len(first) == 19


@pytest.mark.parametrize(
    ("change", "code", "message"),
    [
        ({"claim": "  "}, "INVALID_OBLIGATION", "claim must be nonempty text"),
        ({"criticality": "URGENT"}, "INVALID_OBLIGATION", "Unknown criticality"),
        ({"status": "PROBABLY"}, "INVALID_OBLIGATION", "Unknown obligation status"),
        ({"derivation": "VIBES"}, "INVALID_OBLIGATION", "Unknown derivation"),
        ({"phase": "LATER"}, "INVALID_OBLIGATION", "Unknown compilation phase"),
        ({"mandatory": 1}, "INVALID_OBLIGATION", "mandatory must be a boolean"),
        ({"enforced": None}, "INVALID_OBLIGATION", "enforced must be a boolean"),
        ({"affected_paths": [""]}, "INVALID_OBLIGATION", "Invalid list: affected_paths"),
        (
            {"acceptable_proof_capabilities": ["telepathy"]},
            "INVALID_OBLIGATION",
            "Unknown proof capability",
        ),
    ],
)
def test_an_invalid_obligation_is_refused_with_its_reason(
    change: dict[str, Any], code: str, message: str
) -> None:
    with pytest.raises(ControlError) as caught:
        model.obligation_contract(_obligation(**change))
    assert (caught.value.code, str(caught.value)) == (code, message)


@pytest.mark.parametrize(
    "origin",
    [
        {"generated_reason": "why"},
        {
            "requirement_ids": [],
            "acceptance_ids": ["first"],
            "policy_ids": [],
            "architecture_ids": [],
            "generated_reason": "why",
        },
        {
            "requirement_ids": [],
            "acceptance_ids": [],
            "policy_ids": [],
            "architecture_ids": [],
            "generated_reason": "   ",
        },
        {
            "requirement_ids": [1],
            "acceptance_ids": [],
            "policy_ids": [],
            "architecture_ids": [],
            "generated_reason": "why",
        },
    ],
)
def test_an_obligation_without_usable_provenance_is_refused(origin: dict[str, Any]) -> None:
    with pytest.raises(ControlError) as caught:
        model.obligation_contract(_obligation(origin=origin))
    assert caught.value.code == "INVALID_OBLIGATION"


def test_a_missing_field_names_itself() -> None:
    payload = _obligation()
    del payload["criticality"]
    with pytest.raises(ControlError) as caught:
        model.obligation_contract(payload)
    assert str(caught.value) == "Missing obligation fields: ['criticality']"


def test_merging_a_recompiled_obligation_only_ever_widens_it() -> None:
    previous = _obligation(
        criticality="CRITICAL",
        mandatory=True,
        enforced=True,
        affected_paths=["src/a.py"],
        acceptable_proof_capabilities=["unit", "regression"],
        level=3,
        floor=3,
    )
    candidate = _obligation(
        criticality="LOW",
        mandatory=False,
        enforced=False,
        affected_paths=["src/b.py"],
        acceptable_proof_capabilities=["property"],
        required_verifiers=["digest-b"],
        level=1,
    )

    merged = model.monotonic(previous, candidate)

    assert merged["criticality"] == "CRITICAL"
    assert merged["mandatory"] is True
    assert merged["enforced"] is True
    assert merged["affected_paths"] == ["src/a.py", "src/b.py"]
    assert merged["acceptable_proof_capabilities"] == ["property", "regression", "unit"]
    # The route is replaced, so escalation can move away from a verifier; depth cannot fall.
    assert merged["required_verifiers"] == ["digest-b"]
    assert merged["floor"] == 3


def test_frozen_fields_survive_a_recompile() -> None:
    previous = _obligation(status="WAIVED", waiver_id="WAIV-1", created_at=1.0)
    merged = model.monotonic(previous, _obligation(status="UNRESOLVED", claim="rewritten"))
    assert (merged["status"], merged["waiver_id"], merged["claim"]) == (
        "WAIVED",
        "WAIV-1",
        "The value is one",
    )


@pytest.mark.parametrize(
    ("change", "finding"),
    [
        ({"mandatory": False}, "mandatory obligation would become optional"),
        ({"criticality": "LOW"}, "criticality would be lowered"),
        ({"enforced": False}, "enforced obligation would stop being enforced"),
        (
            {"acceptable_proof_capabilities": []},
            "proof capabilities would be dropped: regression, unit",
        ),
        ({"level": 1, "floor": 1}, "required proof depth would be lowered"),
        ({"required_verifiers": []}, "the claim would be left with no verifier at all"),
    ],
)
def test_every_way_of_asking_for_less_is_named(change: dict[str, Any], finding: str) -> None:
    previous = _obligation(
        criticality="HIGH", acceptable_proof_capabilities=["unit", "regression"], level=2, floor=2
    )
    assert finding in model.contraction(previous, _obligation(**{**previous, **change}))


def test_an_identical_recompile_is_not_a_contraction() -> None:
    previous = _obligation(level=2, floor=2)
    assert model.contraction(previous, dict(previous)) == []


def test_the_plan_digest_ignores_ordering_but_not_strength() -> None:
    left, right = _obligation(id="PO-1"), _obligation(id="PO-2", criticality="HIGH")
    assert model.plan_digest([left, right]) == model.plan_digest([right, left])
    assert model.plan_digest([left, right]) != model.plan_digest(
        [left, {**right, "criticality": "LOW"}]
    )


# --- registry -------------------------------------------------------------------------


def test_the_built_in_registry_describes_what_each_kind_proves() -> None:
    known = registry.Registry()
    assert known.capabilities("unit") == {"unit"}
    assert known.get("mutation")["evidence_class"] == "DETERMINISTIC"
    assert known.get("adversarial")["evidence_class"] == "AGENT_JUDGMENT"
    assert known.get("human")["cost"] == "manual"
    assert "human_judgment" not in known.deterministic_capabilities()
    assert {"falsification", "test_strength"} <= known.deterministic_capabilities()


def test_an_undeclared_kind_claims_no_capability_rather_than_a_convenient_one() -> None:
    entry = registry.Registry().get("bespoke-checks")
    assert entry["capabilities"] == []
    assert entry["declared"] is False
    assert entry["deterministic"] is False
    assert "register it" in entry["note"]


def test_verifiers_supplying_a_capability_come_cheapest_first() -> None:
    assert [e["id"] for e in registry.Registry().supplying("falsification")] == [
        "property",
        "mutation",
    ]
    # A claim about existing behaviour is reachable only by a verifier that says it
    # examines existing behaviour.
    assert [e["id"] for e in registry.Registry().supplying("regression")] == ["regression"]
    assert [e["id"] for e in registry.Registry().supplying("data_preservation")] == ["migration"]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"capabilities": []}, "Declare at least one known capability"),
        ({"capabilities": ["telepathy"]}, "Declare at least one known capability"),
        ({"evidence_class": "HUNCH"}, "Unknown evidence class"),
        ({"cost": "free"}, "Unknown cost class"),
        ({"level": 9}, "Unknown assurance level"),
        ({"id": " "}, "Verifier kind must be nonempty text"),
        (
            {"evidence_class": "DETERMINISTIC", "cost": "manual"},
            "A manual verifier cannot declare deterministic evidence",
        ),
        ({"ecosystems": [""]}, "Invalid list: ecosystems"),
    ],
)
def test_an_invalid_capability_declaration_is_refused(change: dict[str, Any], message: str) -> None:
    base = {
        "id": "golden",
        "capabilities": ["reference_comparison"],
        "evidence_class": "DETERMINISTIC",
        "cost": "low",
        "level": 1,
    }
    with pytest.raises(ControlError) as caught:
        registry.descriptor_contract({**base, **change})
    assert (caught.value.code, str(caught.value)) == ("INVALID_CAPABILITY", message)


def test_a_project_can_register_a_verifier_kind_the_engine_did_not_ship(
    repository: Any,
) -> None:
    service.register_verifier(
        repository,
        {
            "id": "golden-json",
            "capabilities": ["reference_comparison", "regression"],
            "evidence_class": "DETERMINISTIC",
            "cost": "low",
            "level": 1,
            "produced_artifacts": ["artifacts/golden.json"],
        },
    )
    known = service.registry_for(repository)
    assert known.capabilities("golden-json") == {"reference_comparison", "regression"}
    # Registering it again replaces the declaration rather than duplicating it.
    service.register_verifier(
        repository,
        {
            "id": "golden-json",
            "capabilities": ["reference_comparison"],
            "evidence_class": "DETERMINISTIC",
            "cost": "medium",
            "level": 1,
        },
    )
    assert service.registry_for(repository).get("golden-json")["cost"] == "medium"
    assert len(repository.store.list("verifier_capability")) == 1


# --- compiler -------------------------------------------------------------------------


def test_risk_signals_come_from_the_existing_deterministic_patterns() -> None:
    assert compiler.signals(["src/auth/login.py"]) == ["auth"]
    assert compiler.signals(["src/report.py"]) == []
    assert "money" in compiler.signals(["src/billing/invoice.py"])


def test_compiling_the_same_inputs_twice_produces_the_same_obligations(
    repository: Any,
) -> None:
    task_id, _ = claimed(repository, contract(risk="HIGH"))
    task = repository.store.get(task_id, "task")
    known = service.registry_for(repository)

    first = compiler.compile_obligations(repository, task, known, phase="INITIAL")
    second = compiler.compile_obligations(repository, task, known, phase="INITIAL")

    assert first == second


def test_an_acceptance_obligation_states_the_criterion_and_cites_its_verifiers(
    repository: Any,
) -> None:
    task_id, _ = claimed(
        repository,
        contract(
            acceptance=["The reported value is one", "Access rules hold"],
            verification=[spec("unit", [0]), spec("security", [1])],
        ),
    )
    plan = service.compile_plan(repository, task_id, phase="INITIAL")
    obligations = {
        o["claim"]: o for o in (repository.store.get(i, "obligation") for i in plan["obligations"])
    }

    first = obligations["The reported value is one"]
    assert first["derivation"] == "CONTRACT"
    assert first["origin"]["acceptance_ids"] == [0]
    assert (
        first["origin"]["generated_reason"] == "acceptance criterion declared in the task contract"
    )
    assert first["acceptable_proof_capabilities"] == ["unit"]
    assert len(first["required_verifiers"]) == 1
    assert obligations["Access rules hold"]["acceptable_proof_capabilities"] == [
        "authorization_boundary",
        "security",
    ]


def test_a_policy_obligation_records_the_surface_that_raised_it(repository: Any) -> None:
    task_id, _ = claimed(repository, contract(risk="STANDARD"))
    sources(repository.root, {"src/billing/invoice.py": "total = 0\n"})
    service.reconcile(repository, task_id)

    money = policy_obligation(repository, task_id, "FIN-STABLE")

    assert money["derivation"] == "POLICY"
    assert money["criticality"] == "CRITICAL"
    assert money["mandatory"] is True
    assert money["affected_paths"] == ["src/billing/invoice.py"]
    assert money["origin"]["generated_reason"] == (
        "observed money surface in src/billing/invoice.py"
    )
    assert money["origin"]["acceptance_ids"] == []


def test_a_forecast_obligation_is_recorded_but_not_enforced_until_the_diff_confirms_it(
    repository: Any,
) -> None:
    task_id, _ = claimed(repository, contract(scope=["src/auth"]))
    sources(repository.root, {"src/auth/login.py": "def login():\n    return True\n"})
    service.compile_plan(repository, task_id, phase="INITIAL")

    forecast = policy_obligation(repository, task_id, "SEC-AUTHZ")
    assert (forecast["phase"], forecast["enforced"]) == ("INITIAL", False)
    assert service.status(repository, task_id)["tasks"][0]["required"] == 1

    service.reconcile(repository, task_id)

    confirmed = policy_obligation(repository, task_id, "SEC-AUTHZ")
    assert (confirmed["phase"], confirmed["enforced"]) == ("RECONCILED", True)
    assert service.status(repository, task_id)["tasks"][0]["required"] == 2


def test_high_risk_adds_a_falsification_obligation_and_low_risk_does_not(
    repository: Any,
) -> None:
    for risk, expected in (("LOW", 0), ("STANDARD", 0), ("HIGH", 1), ("CRITICAL", 1)):
        task_id = planned(repository, contract(risk=risk))
        plan = service.compile_plan(repository, task_id, phase="INITIAL")
        found = [
            o
            for o in (repository.store.get(i, "obligation") for i in plan["obligations"])
            if "TEST-STRENGTH" in o["origin"]["policy_ids"]
        ]
        assert len(found) == expected, risk


def test_only_critical_risk_asks_for_recorded_human_acceptance(repository: Any) -> None:
    for risk, expected in (("HIGH", 0), ("CRITICAL", 1)):
        task_id = planned(repository, contract(risk=risk))
        plan = service.compile_plan(repository, task_id, phase="INITIAL")
        found = [
            o
            for o in (repository.store.get(i, "obligation") for i in plan["obligations"])
            if "HUMAN-ACCEPTANCE" in o["origin"]["policy_ids"]
        ]
        assert len(found) == expected, risk


def test_observed_symbols_are_attached_to_the_obligations_over_their_own_paths(
    repository: Any,
) -> None:
    task_id, _ = claimed(repository, contract(risk="STANDARD"))
    sources(repository.root, {"src/auth/login.py": "def login():\n    return True\n"})
    repository.reconcile()
    service.reconcile(repository, task_id)

    authorization = policy_obligation(repository, task_id, "SEC-AUTHZ")
    assert authorization["affected_symbols"] == ["src/auth/login.py::login"]


# --- planner --------------------------------------------------------------------------


def _route(repository: Any, obligation: dict[str, Any], kinds: list[str], floor: int = 1) -> Any:
    task = {"verification": [spec(kind, [0], PASSES) for kind in kinds]}
    known = service.registry_for(repository)
    return planner.plan_for(obligation, planner.pool(task, known), known, floor=floor)


def test_the_planner_picks_the_cheapest_sufficient_route(repository: Any) -> None:
    obligation = _obligation(
        acceptable_proof_capabilities=["regression", "historical_stability", "property"],
        criticality="CRITICAL",
        derivation="POLICY",
    )
    route = _route(repository, obligation, ["regression", "mutation"])
    assert route["route"] == "regression supplies historical_stability (DETERMINISTIC, medium cost)"
    assert route["level"] == 2


def test_equally_cheap_deterministic_routes_are_chosen_by_a_stable_order(
    repository: Any,
) -> None:
    """Neither of these is cheaper, so the pick is stable rather than incidental."""
    obligation = _obligation(acceptable_proof_capabilities=["behavioral"], derivation="POLICY")
    first = _route(repository, obligation, ["acceptance", "integration"])
    second = _route(repository, obligation, ["integration", "acceptance"])
    assert first["route"] == second["route"]
    assert first["route"].startswith("acceptance supplies behavioral")


def test_falsification_is_preferred_among_equally_cheap_routes(repository: Any) -> None:
    obligation = _obligation(
        acceptable_proof_capabilities=["integration", "property"], derivation="POLICY"
    )
    route = _route(repository, obligation, ["integration", "property"])
    assert route["route"].startswith("property supplies property")


def test_a_human_only_claim_gets_a_named_human_verifier(repository: Any) -> None:
    obligation = _obligation(
        acceptable_proof_capabilities=["human_judgment"], derivation="POLICY", id="PO-x"
    )
    route = _route(repository, obligation, ["unit"])
    assert route["human_required"] is True
    assert route["selected"] == ["human:PO-x"]
    assert route["level"] == 4


def test_a_claim_no_declared_verifier_reaches_is_reported_not_guessed(
    repository: Any,
) -> None:
    obligation = _obligation(
        acceptable_proof_capabilities=["migration_safety"], derivation="POLICY"
    )
    route = _route(repository, obligation, ["unit"])
    assert route["selected"] == []
    assert route["unsatisfiable"] == ["migration_safety"]
    assert route["human_required"] is False
    assert "no declared verifier supplies" in route["route"]


def test_raising_the_floor_moves_off_the_route_that_could_not_answer(
    repository: Any,
) -> None:
    obligation = _obligation(
        acceptable_proof_capabilities=["falsification", "test_strength"], derivation="POLICY"
    )
    shallow = _route(repository, obligation, ["property", "mutation"], floor=1)
    deeper = _route(repository, obligation, ["property", "mutation"], floor=3)
    assert shallow["route"].startswith("property supplies")
    assert deeper["route"].startswith("mutation supplies")
    assert (shallow["level"], deeper["level"]) == (2, 3)


def test_a_contract_obligation_keeps_the_verifiers_its_own_contract_bound(
    repository: Any,
) -> None:
    task_id, _ = claimed(
        repository,
        contract(
            acceptance=["The value is one"],
            verification=[spec("unit", [0]), spec("acceptance", [0])],
        ),
    )
    task = repository.store.get(task_id, "task")
    known = service.registry_for(repository)
    compiled = compiler.compile_obligations(repository, task, known, phase="INITIAL")
    planned = planner.plan(task, compiled["obligations"], known)

    assert len(planned[0]["required_verifiers"]) == 2
    assert planned[0]["plan"]["route"].startswith("verifiers the task contract bound")


# --- resolver -------------------------------------------------------------------------


def test_a_narrow_obligation_binding_covers_only_its_own_paths(repository: Any) -> None:
    task_id, _ = claimed(repository)
    task = repository.store.get(task_id, "task")
    narrow = _obligation(task_id=task_id, affected_paths=["src/report.py"])
    wide = _obligation(task_id=task_id, affected_paths=[])

    assert set(resolver.obligation_binding(repository, task, narrow)["files"]) == {"src/report.py"}
    assert set(resolver.obligation_binding(repository, task, wide)["files"]) == {
        "src/report.py",
        "src/other.py",
    }


def test_the_binding_moves_when_the_claim_its_verifiers_or_its_policy_move(
    repository: Any,
) -> None:
    task_id, _ = claimed(repository)
    task = repository.store.get(task_id, "task")
    base = _obligation(task_id=task_id, affected_paths=["src/report.py"])
    original = resolver.obligation_binding(repository, task, base)

    assert resolver.obligation_binding(repository, task, {**base, "claim": "other"}) != original
    assert (
        resolver.obligation_binding(repository, task, {**base, "required_verifiers": ["x"]})
        != original
    )
    repository.approve_command(["python", "-V"])
    assert resolver.obligation_binding(repository, task, base) != original


def test_evidence_is_only_read_for_the_obligations_it_was_recorded_against() -> None:
    contract_obligation = _obligation(id="PO-1", derivation="CONTRACT")
    policy = _obligation(
        id="PO-2", derivation="POLICY", origin={**_obligation()["origin"], "acceptance_ids": []}
    )
    stamped = {"obligation_ids": ["PO-2"], "acceptance": [0]}
    legacy = {"obligation_ids": [], "acceptance": [0]}

    assert resolver.matches(stamped, policy) is True
    assert resolver.matches(stamped, contract_obligation) is True
    # A 2.0 record still proves an acceptance criterion; it proves no policy claim.
    assert resolver.matches(legacy, contract_obligation) is True
    assert resolver.matches(legacy, policy) is False


def test_a_run_whose_inputs_moved_under_it_proves_nothing() -> None:
    assert resolver.run_consistent({"run_consistent": True}) is True
    assert resolver.run_consistent({"run_consistent": False}) is False
    # A 2.0 record has no such field, so its conservative stale flag is the only signal.
    assert resolver.run_consistent({"stale": False}) is True
    assert resolver.run_consistent({"stale": True}) is False


def test_unknown_is_never_pass(repository: Any) -> None:
    """An obligation no verifier reaches stays UNKNOWN and keeps its proof debt."""
    task_id, _ = claimed(repository, contract(risk="HIGH"))
    service.reconcile(repository, task_id)
    strength = policy_obligation(repository, task_id, "TEST-STRENGTH")
    task = repository.store.get(task_id, "task")

    resolution = resolver.resolve(
        repository, task, strength, evidence=resolver.task_evidence(repository, task["id"])
    )

    assert resolution["status"] == "UNKNOWN"
    assert resolution["status"] not in model.RESOLVED
    assert strength["id"] in [
        i["obligation_id"] for i in resolver.debt(repository, task)["outstanding"]
    ]


def test_proof_debt_counts_only_mandatory_confirmed_obligations(repository: Any) -> None:
    task_id, _ = claimed(repository, contract(scope=["src/auth"]))
    sources(repository.root, {"src/auth/login.py": "def login():\n    return True\n"})
    service.compile_plan(repository, task_id, phase="INITIAL")
    task = repository.store.get(task_id, "task")

    report = resolver.debt(repository, task)

    assert report["obligations"] == 2
    # The forecast authorization obligation is recorded but not yet confirmed by a diff,
    # so it is visible in the counts and absent from what completion requires.
    assert report["required"] == 1
    assert report["proof_debt"] == 1
    assert report["required_counts"] == {"UNRESOLVED": 1}
    assert sorted(report["counts"]) == ["UNKNOWN", "UNRESOLVED"]
