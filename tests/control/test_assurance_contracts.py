"""The exact shape of what the assurance engine declares and returns, field by field.

The mutation campaign over the assurance package left survivors wherever a test checked
one field of a record and let the rest change unnoticed: a rule's capabilities, a report's
keys, a reason an operator reads. These cases pin whole records, so any change to what the
engine says is a reviewed change rather than a silent one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from assurance_support import FAILS, checkpoint, claimed, contract, sources, spec

from agentic_discipline.control.assurance import (
    compiler,
    decision,
    impact,
    migration,
    model,
    planner,
    registry,
    resolver,
    service,
)
from agentic_discipline.control.assurance.resolver import obligations_for
from agentic_discipline.control.contracts import ControlError
from agentic_discipline.control.plane import Plane, adopt
from agentic_discipline.control.verification import complete


@pytest.fixture
def repository(tmp_path: Path) -> Any:
    sources(tmp_path, {"src/report.py": "value = 1\n", "src/other.py": "unrelated = True\n"})
    adopt(tmp_path)
    with Plane(tmp_path) as plane:
        yield plane


def _two_point_zero(plane: Any) -> None:
    with plane.store.transaction():
        plane.store.db.execute("UPDATE meta SET value='1' WHERE key='schema_version'")
    plane.store.schema_version = 1


# --- the completion invariant, isolated ------------------------------------------------


def test_completion_is_refused_for_proof_debt_even_when_every_contract_verifier_passed(
    repository: Any,
) -> None:
    """The one refusal the 2.0 gate cannot give: its own proof holds, a claim does not."""
    task_id, session = claimed(repository, contract(risk="HIGH"))
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    repository.checkpoint(task_id, session, checkpoint())
    task = repository.store.get(task_id, "task")
    # The whole 2.0 condition set holds.
    assert task["state"] == "VERIFYING"
    from agentic_discipline.control.verification import completion_proof

    assert completion_proof(repository, task)

    with pytest.raises(ControlError) as caught:
        complete(repository, task_id, session)

    strength = next(
        o
        for o in obligations_for(repository, task_id)
        if "TEST-STRENGTH" in o["origin"]["policy_ids"]
    )
    assert (caught.value.code, str(caught.value)) == (
        "PROOF_DEBT",
        f"Mandatory proof obligations are unresolved: {strength['id']} UNKNOWN",
    )
    assert repository.store.get(task_id, "task")["state"] == "VERIFYING"


def test_mandatory_debt_is_the_outstanding_list_itself(repository: Any) -> None:
    task_id, session = claimed(repository, contract(risk="HIGH"))
    service.reconcile(repository, task_id)
    service.verify(repository, task_id, session)
    task = repository.store.get(task_id, "task")

    assert (
        decision.mandatory_debt(repository, task) == resolver.debt(repository, task)["outstanding"]
    )
    assert [i["status"] for i in decision.mandatory_debt(repository, task)] == ["UNKNOWN"]


# --- the capability registry, as declared ---------------------------------------------

REGISTRY = [
    ("acceptance", ["acceptance", "behavioral"], "DETERMINISTIC", "medium", 1, True),
    ("adversarial", ["falsification_review"], "AGENT_JUDGMENT", "high", 3, False),
    ("architecture", ["architecture"], "DETERMINISTIC", "low", 1, True),
    (
        "contract",
        ["contract_compatibility", "schema_compatibility"],
        "DETERMINISTIC",
        "low",
        1,
        True,
    ),
    ("coverage", ["coverage"], "MEASURED", "medium", 2, False),
    ("human", ["human_judgment"], "HUMAN", "manual", 4, False),
    ("integration", ["behavioral", "integration"], "DETERMINISTIC", "medium", 2, False),
    ("migration", ["data_preservation", "migration_safety"], "DETERMINISTIC", "high", 2, False),
    ("mutation", ["falsification", "test_strength"], "DETERMINISTIC", "high", 3, True),
    ("property", ["falsification", "invariant", "property"], "DETERMINISTIC", "medium", 2, False),
    ("reference", ["reference_comparison"], "DETERMINISTIC", "low", 1, True),
    (
        "reference-review",
        ["qualitative_reference_comparison"],
        "AGENT_JUDGMENT",
        "medium",
        3,
        False,
    ),
    ("regression", ["historical_stability", "regression"], "DETERMINISTIC", "medium", 2, True),
    ("schema", ["migration_safety", "schema_compatibility"], "DETERMINISTIC", "low", 1, True),
    ("security", ["authorization_boundary", "security"], "DETERMINISTIC", "medium", 2, False),
    ("static", ["static_analysis"], "DETERMINISTIC", "low", 1, True),
    ("unit", ["unit"], "DETERMINISTIC", "low", 1, True),
]


def test_the_built_in_registry_is_exactly_what_it_declares() -> None:
    assert registry.Registry().describe() == [
        {
            "id": kind,
            "capabilities": capabilities,
            "evidence_class": evidence_class,
            "cost": cost,
            "level": level,
            "supports_incremental": incremental,
            "ecosystems": ["*"],
            "required_inputs": [],
            "produced_artifacts": [],
            "deterministic": evidence_class == "DETERMINISTIC",
            "declared": True,
        }
        for kind, capabilities, evidence_class, cost, level, incremental in REGISTRY
    ]


def test_an_undeclared_kind_is_described_completely_and_honestly() -> None:
    assert registry.Registry().get("bespoke") == {
        "id": "bespoke",
        "capabilities": [],
        "evidence_class": "MEASURED",
        "cost": "medium",
        "level": 1,
        "supports_incremental": False,
        "deterministic": False,
        "declared": False,
        "ecosystems": ["*"],
        "required_inputs": [],
        "produced_artifacts": [],
        "note": "kind is not in the capability registry; register it to let the planner use it",
    }


def test_a_registered_kind_takes_explicit_defaults_for_what_it_did_not_say(
    repository: Any,
) -> None:
    returned = service.register_verifier(
        repository,
        {
            "id": "golden",
            "capabilities": ["reference_comparison"],
            "evidence_class": "DETERMINISTIC",
            "cost": "low",
            "level": 1,
        },
    )
    expected = {
        "id": "golden",
        "capabilities": ["reference_comparison"],
        "evidence_class": "DETERMINISTIC",
        "cost": "low",
        "level": 1,
        "supports_incremental": False,
        "ecosystems": ["*"],
        "required_inputs": [],
        "produced_artifacts": [],
        "deterministic": True,
        "declared": True,
    }
    assert {k: v for k, v in returned.items() if k != "version"} == expected
    assert returned["version"] == 1
    assert service.registry_for(repository).get("golden") == expected


@pytest.mark.parametrize("level", [0, 1, 2, 3, 4])
def test_every_assurance_level_can_be_declared(level: int) -> None:
    registry.descriptor_contract(
        {
            "id": "k",
            "capabilities": ["unit"],
            "evidence_class": "MEASURED",
            "cost": "low",
            "level": level,
        }
    )


def test_a_level_outside_the_ladder_is_refused() -> None:
    with pytest.raises(ControlError):
        registry.descriptor_contract(
            {
                "id": "k",
                "capabilities": ["unit"],
                "evidence_class": "MEASURED",
                "cost": "low",
                "level": 5,
            }
        )


def test_a_missing_capability_field_names_itself() -> None:
    with pytest.raises(ControlError) as caught:
        registry.descriptor_contract({"id": "k", "capabilities": ["unit"]})
    assert (caught.value.code, str(caught.value)) == (
        "INVALID_CAPABILITY",
        "Missing verifier capability fields: ['cost', 'evidence_class', 'level']",
    )


def test_the_registry_view_names_what_is_deterministic(repository: Any) -> None:
    view = service.registry(repository)
    assert view["verifiers"] == registry.Registry().describe()
    assert view["deterministic_capabilities"] == sorted(
        registry.Registry().deterministic_capabilities()
    )
    assert view["note"] == "a task contract supplies the argv; this describes what each kind proves"


# --- the policy rules, as declared -----------------------------------------------------

RULES = {
    "src/auth/login.py": (
        "SEC-AUTHZ",
        "auth",
        "Unauthorized callers cannot reach the operations this change touches.",
        ["authorization_boundary", "security"],
        "HIGH",
    ),
    "src/billing/invoice.py": (
        "FIN-STABLE",
        "money",
        "Financial results for existing data are unchanged by this change.",
        ["historical_stability", "regression"],
        "CRITICAL",
    ),
    "migrations/0001.sql": (
        "MIG-SAFE",
        "migration",
        "The migration preserves the data that already exists.",
        ["data_preservation", "migration_safety"],
        "CRITICAL",
    ),
    "src/api/routes.py": (
        "API-COMPAT",
        "public_api",
        "The published interface stays compatible for existing callers.",
        ["contract_compatibility", "schema_compatibility"],
        "HIGH",
    ),
    "src/lock.py": (
        "CONC-SAFE",
        "concurrency",
        "Concurrent execution cannot observe or produce an inconsistent state.",
        ["integration", "invariant", "property"],
        "HIGH",
    ),
    "src/security/token.py": (
        "SEC-GENERAL",
        "security",
        "The change introduces no new way to read or forge protected data.",
        ["security", "static_analysis"],
        "HIGH",
    ),
    "src/crypto/cipher.py": (
        "CRYPTO-SAFE",
        "crypto",
        "Cryptographic behaviour matches its specified algorithm and parameters.",
        ["property", "regression", "security"],
        "CRITICAL",
    ),
    "src/purge.py": (
        "DEL-SAFE",
        "destructive",
        "Destructive operations remove only what their contract allows.",
        ["acceptance", "property", "regression"],
        "HIGH",
    ),
    "src/domain/model.py": (
        "ARCH-BOUND",
        "architecture",
        "Declared architecture boundaries are not crossed by this change.",
        ["architecture", "static_analysis"],
        "HIGH",
    ),
    "deploy/ci/pipeline.yml": (
        "INFRA-SAFE",
        "infra",
        "Deployment and pipeline configuration remains executable as declared.",
        ["integration", "static_analysis"],
        "STANDARD",
    ),
}
TASK = {
    "id": "TASK-1",
    "risk": "LOW",
    "requirements": ["ENT-R"],
    "scope": ["src"],
    "boundaries": [],
}


@pytest.mark.parametrize("path", sorted(RULES))
def test_each_policy_rule_raises_exactly_the_obligation_it_declares(path: str) -> None:
    policy_id, signal, claim, capabilities, criticality = RULES[path]

    (obligation,) = compiler.policy_obligations(TASK, [path], phase="RECONCILED", enforced=True)

    assert obligation == {
        "id": model.obligation_id("TASK-1", f"policy:{policy_id}"),
        "task_id": "TASK-1",
        "claim": claim,
        "origin": {
            "requirement_ids": ["ENT-R"],
            "acceptance_ids": [],
            "policy_ids": [policy_id],
            "architecture_ids": [],
            "generated_reason": f"observed {signal} surface in {path}",
        },
        "derivation": "POLICY",
        "criticality": criticality,
        "mandatory": True,
        "status": "UNRESOLVED",
        "phase": "RECONCILED",
        "enforced": True,
        "acceptable_proof_capabilities": capabilities,
        "required_verifiers": [],
        "affected_paths": [path],
        "affected_symbols": [],
        "dependencies": [],
    }
    assert compiler.signals([path]) == [signal]


def test_a_policy_reason_names_at_most_five_of_the_paths_that_raised_it() -> None:
    paths = [f"src/auth/p{i}.py" for i in range(7)]
    (obligation,) = compiler.policy_obligations(TASK, paths, phase="RECONCILED", enforced=True)
    assert obligation["origin"]["generated_reason"] == (
        "observed auth surface in " + ", ".join(sorted(paths)[:5])
    )
    assert obligation["affected_paths"] == sorted(paths)


def test_a_reached_policy_says_how_it_was_reached() -> None:
    (obligation,) = compiler.policy_obligations(
        TASK,
        ["src/auth/login.py"],
        phase="RECONCILED",
        enforced=True,
        derivation="IMPACT",
        because="recorded dependencies",
    )
    assert obligation["derivation"] == "IMPACT"
    assert obligation["origin"]["generated_reason"] == (
        "observed auth surface in src/auth/login.py; reached through recorded dependencies"
    )


def test_the_risk_signals_read_paths_case_insensitively_and_one_per_line() -> None:
    assert compiler.signals(["SRC/AUTH/Login.py"]) == ["auth"]
    # Joined with newlines, so a signal never spans two paths.
    assert compiler.signals(["src/pay", "ment.py"]) == []


def test_the_falsification_and_human_rules_are_exactly_what_they_declare() -> None:
    task = {**TASK, "risk": "CRITICAL"}
    (strength,) = compiler.falsification_obligation(
        task, ["src/a.py"], phase="RECONCILED", enforced=True
    )
    (accepted,) = compiler.human_obligation(task, [], phase="INITIAL", enforced=False)

    assert (
        strength["claim"],
        strength["acceptable_proof_capabilities"],
        strength["criticality"],
        strength["origin"]["policy_ids"],
        strength["origin"]["requirement_ids"],
        strength["origin"]["generated_reason"],
    ) == (
        "The tests covering this change detect meaningful implementation errors.",
        ["falsification", "falsification_review", "test_strength"],
        "CRITICAL",
        ["TEST-STRENGTH"],
        ["ENT-R"],
        "CRITICAL risk requires falsifying the strength of its tests",
    )
    assert (
        accepted["claim"],
        accepted["acceptable_proof_capabilities"],
        accepted["criticality"],
        accepted["affected_paths"],
        accepted["origin"]["generated_reason"],
        accepted["enforced"],
    ) == (
        "A human explicitly accepted this critical change.",
        ["human_judgment"],
        "CRITICAL",
        ["src"],
        "CRITICAL risk requires a recorded human acceptance of src",
        False,
    )


def test_human_acceptance_names_at_most_five_observed_paths() -> None:
    task = {**TASK, "risk": "CRITICAL"}
    paths = [f"src/m{i}.py" for i in range(7)]
    (accepted,) = compiler.human_obligation(task, paths, phase="RECONCILED", enforced=True)
    assert accepted["origin"]["generated_reason"] == (
        "CRITICAL risk requires a recorded human acceptance of " + ", ".join(sorted(paths)[:5])
    )


# --- the compiler, when the same rule is raised twice ---------------------------------


def test_a_rule_raised_by_a_changed_path_and_a_reached_path_is_one_obligation(
    repository: Any,
) -> None:
    sources(repository.root, {"src/auth/session.py": "def check():\n    return True\n"})
    repository.reconcile()
    reached_file = next(
        e
        for e in repository.store.list("entity")
        if e.get("type") == "file" and e["source_ref"] == "src/auth/session.py"
    )
    changed_owner = repository.knowledge.apply(
        [
            {
                "name": "src/auth/login.py owner",
                "graph": "code",
                "type": "module",
                "source_ref": "src/auth/login.py",
                "authority": "code",
                "confidence": 1,
                "observation": "OBSERVED",
            }
        ],
        repository.store.knowledge_version,
        "record the module",
    )["entities"][0]
    del changed_owner
    task_id, _ = claimed(repository, contract(risk="STANDARD"))
    sources(repository.root, {"src/auth/login.py": "def login():\n    return True\n"})
    repository.reconcile()
    changed_file = next(
        e
        for e in repository.store.list("entity")
        if e.get("type") == "file" and e["source_ref"] == "src/auth/login.py"
    )
    repository.knowledge.link(reached_file["id"], changed_file["id"], "depends_on")

    plan = service.reconcile(repository, task_id)

    assert plan["impact"]["dependent_paths"] == ["src/auth/session.py"]
    authorizations = [
        o for o in obligations_for(repository, task_id) if "SEC-AUTHZ" in o["origin"]["policy_ids"]
    ]
    assert len(authorizations) == 1
    assert authorizations[0]["affected_paths"] == ["src/auth/login.py", "src/auth/session.py"]
    assert authorizations[0]["derivation"] == "POLICY"
    assert (authorizations[0]["mandatory"], authorizations[0]["enforced"]) == (True, True)


# --- impact ----------------------------------------------------------------------------


def _requirement(plane: Any, name: str, authority: str = "contract") -> dict[str, Any]:
    return plane.knowledge.apply(
        [
            {
                "name": name,
                "graph": "requirement",
                "type": "requirement",
                "source_ref": "specs/requirements.md",
                "authority": authority,
                "confidence": 1,
                "observation": "DECLARED",
            }
        ],
        plane.store.knowledge_version,
        "approved requirement",
    )["entities"][0]


def _file(plane: Any, path: str) -> dict[str, Any]:
    plane.reconcile()
    return next(
        e for e in plane.store.list("entity") if e.get("type") == "file" and e["source_ref"] == path
    )


def test_reaching_follows_only_the_changed_files_and_reports_only_files_as_paths(
    repository: Any,
) -> None:
    near = _requirement(repository, "FR-1 reporting")
    far = _requirement(repository, "FR-2 unrelated")
    repository.knowledge.link(
        near["id"], _file(repository, "src/report.py")["id"], "implemented_by"
    )
    repository.knowledge.link(far["id"], _file(repository, "src/other.py")["id"], "implemented_by")

    assert impact.reached(repository, ["src/report.py"]) == {
        "changed_paths": ["src/report.py"],
        "observed_symbols": [],
        "dependent_requirements": [near["id"]],
        "dependent_paths": [],
        "resolution": "recorded links between measured files, symbols and requirements",
        "unresolved": "cross-language call graphs and runtime reachability remain UNKNOWN",
    }


def test_reaching_stops_three_links_away(repository: Any) -> None:
    chain = [_requirement(repository, f"FR-{i}") for i in range(4)]
    repository.knowledge.link(
        chain[0]["id"], _file(repository, "src/report.py")["id"], "implemented_by"
    )
    for later, earlier in zip(chain[1:], chain[:-1], strict=True):
        repository.knowledge.link(later["id"], earlier["id"], "depends_on")

    reached = impact.reached(repository, ["src/report.py"])

    assert reached["dependent_requirements"] == sorted(c["id"] for c in chain[:3])


def test_an_impact_obligation_is_enforced_and_mandatory_only_for_contract_authority(
    repository: Any,
) -> None:
    binding = _requirement(repository, "FR-9 contract", "contract")
    advisory = _requirement(repository, "FR-10 documented", "documentation")
    target = _file(repository, "src/other.py")
    repository.knowledge.link(binding["id"], target["id"], "implemented_by")
    repository.knowledge.link(advisory["id"], target["id"], "implemented_by")
    task_id, _ = claimed(repository)

    (repository.root / "src" / "other.py").write_text("unrelated = False\n", encoding="utf-8")
    service.reconcile(repository, task_id)

    reached = {
        o["origin"]["requirement_ids"][0]: o
        for o in obligations_for(repository, task_id)
        if o["derivation"] == "IMPACT"
    }
    assert set(reached) == {binding["id"], advisory["id"]}
    for requirement, mandatory in ((binding["id"], True), (advisory["id"], False)):
        obligation = reached[requirement]
        assert (obligation["phase"], obligation["enforced"], obligation["mandatory"]) == (
            "RECONCILED",
            True,
            mandatory,
        )
        assert obligation["acceptable_proof_capabilities"] == [
            "acceptance",
            "integration",
            "regression",
        ]
        assert obligation["criticality"] == "STANDARD"
    assert service.status(repository, task_id)["tasks"][0]["required"] == 2


# --- the model -------------------------------------------------------------------------


def test_depth_defaults_to_the_shallowest_level() -> None:
    assert model.depth({}) == 1
    assert model.depth({"level": 3}) == 3
    assert model.depth({"level": 3, "floor": 4}) == 4


def test_a_candidate_that_says_nothing_about_a_field_does_not_weaken_it() -> None:
    previous = {
        "mandatory": True,
        "enforced": True,
        "criticality": "LOW",
        "acceptable_proof_capabilities": [],
        "required_verifiers": [],
    }
    assert model.contraction(previous, {}) == []


@pytest.mark.parametrize(
    ("field", "value", "finding"),
    [
        ("mandatory", False, "mandatory obligation would become optional"),
        ("enforced", False, "enforced obligation would stop being enforced"),
    ],
)
def test_only_an_explicit_weakening_is_named(field: str, value: bool, finding: str) -> None:
    previous = {
        "mandatory": True,
        "enforced": True,
        "criticality": "LOW",
        "acceptable_proof_capabilities": [],
        "required_verifiers": [],
    }
    assert model.contraction(previous, {field: value}) == [finding]


def test_the_frozen_and_origin_fields_are_the_declared_ones() -> None:
    assert model.FROZEN == {
        "id",
        "version",
        "task_id",
        "claim",
        "status",
        "waiver_id",
        "created_at",
        "human_request",
    }
    assert model.LEVELS == (0, 1, 2, 3, 4)
    assert model.EVIDENCE_CLASSES == ("DETERMINISTIC", "MEASURED", "AGENT_JUDGMENT", "HUMAN")
    assert "VERIFYING" in model.STATUSES
    assert {"architecture", "coverage", "qualitative_reference_comparison"} <= model.CAPABILITIES


def test_frozen_fields_keep_their_stored_values_through_a_merge() -> None:
    previous = {
        "id": "PO-1",
        "version": 3,
        "task_id": "TASK-1",
        "claim": "stored",
        "status": "WAIVED",
        "waiver_id": "WAIV-1",
        "created_at": 1.0,
        "human_request": "asked",
        "mandatory": True,
        "enforced": True,
        "criticality": "LOW",
        "affected_paths": [],
        "affected_symbols": ["a"],
        "acceptable_proof_capabilities": [],
        "required_verifiers": [],
        "dependencies": ["PO-0"],
    }
    candidate = {
        **{k: f"new-{k}" for k in model.FROZEN},
        "mandatory": True,
        "enforced": True,
        "criticality": "LOW",
        "affected_paths": [],
        "affected_symbols": ["b"],
        "acceptable_proof_capabilities": [],
        "required_verifiers": ["V"],
        "dependencies": ["PO-9"],
    }

    merged = model.monotonic(previous, candidate)

    assert {k: merged[k] for k in model.FROZEN} == {k: previous[k] for k in model.FROZEN}
    assert merged["affected_symbols"] == ["a", "b"]
    assert merged["dependencies"] == ["PO-0", "PO-9"]
    assert merged["floor"] == 1


@pytest.mark.parametrize(
    ("origin_change", "message"),
    [
        ({"generated_reason": "  "}, "Provenance needs the reason this obligation exists"),
        ({"acceptance_ids": [-1]}, "Acceptance provenance must be criterion indexes"),
        ({"policy_ids": [""]}, "Invalid provenance list: policy_ids"),
    ],
)
def test_each_provenance_defect_names_itself(origin_change: dict[str, Any], message: str) -> None:
    obligation = {
        "task_id": "TASK-1",
        "claim": "c",
        "origin": {
            "requirement_ids": [],
            "acceptance_ids": [],
            "policy_ids": [],
            "architecture_ids": [],
            "generated_reason": "why",
            **origin_change,
        },
        "derivation": "POLICY",
        "criticality": "LOW",
        "mandatory": True,
        "status": "UNRESOLVED",
        "phase": "INITIAL",
        "enforced": True,
        "acceptable_proof_capabilities": [],
        "required_verifiers": [],
        "affected_paths": [],
        "affected_symbols": [],
        "dependencies": [],
    }
    with pytest.raises(ControlError) as caught:
        model.obligation_contract(obligation)
    assert str(caught.value) == message


def test_an_obligation_with_no_provenance_block_says_so() -> None:
    with pytest.raises(ControlError) as caught:
        model.obligation_contract(
            {
                "task_id": "T",
                "claim": "c",
                "origin": [],
                "derivation": "POLICY",
                "criticality": "LOW",
                "mandatory": True,
                "status": "UNRESOLVED",
                "phase": "INITIAL",
                "enforced": True,
                "acceptable_proof_capabilities": [],
                "required_verifiers": [],
                "affected_paths": [],
                "affected_symbols": [],
                "dependencies": [],
            }
        )
    assert str(caught.value) == "Obligation lacks provenance"


# --- the planner -----------------------------------------------------------------------


def _pool(kinds: list[str]) -> list[dict[str, Any]]:
    task = {"verification": [spec(kind, [0]) for kind in kinds]}
    return planner.pool(task, registry.Registry())


def test_a_claim_with_no_acceptable_capability_says_none_was_declared() -> None:
    route = planner.plan_for(
        {"id": "PO-1", "acceptable_proof_capabilities": [], "criticality": "LOW"},
        _pool(["unit"]),
        registry.Registry(),
    )
    assert route == {
        "level": 1,
        "selected": [],
        "covered": [],
        "route": "no declared verifier supplies an acceptable capability at depth 1 or deeper: "
        "none declared",
        "human_required": False,
        "unsatisfiable": [],
        "deterministic_available": [],
    }


def test_a_selected_route_is_described_completely() -> None:
    specs = _pool(["regression"])
    route = planner.plan_for(
        {
            "id": "PO-1",
            "acceptable_proof_capabilities": ["historical_stability"],
            "criticality": "LOW",
        },
        specs,
        registry.Registry(),
    )
    assert route == {
        "level": 2,
        "selected": [specs[0]["digest"]],
        "covered": ["historical_stability"],
        "route": "regression supplies historical_stability (DETERMINISTIC, medium cost)",
        "human_required": False,
        "unsatisfiable": [],
        "deterministic_available": ["historical_stability"],
    }


def test_a_human_route_is_described_completely() -> None:
    assert planner.plan_for(
        {"id": "PO-7", "acceptable_proof_capabilities": ["human_judgment"], "criticality": "LOW"},
        _pool(["unit"]),
        registry.Registry(),
    ) == {
        "level": 4,
        "selected": ["human:PO-7"],
        "covered": ["human_judgment"],
        "route": "human resolution; no automated verifier can settle this claim",
        "human_required": True,
        "unsatisfiable": [],
        "deterministic_available": [],
    }


def test_the_pool_carries_each_verifier_as_the_contract_declared_it() -> None:
    (entry,) = _pool(["unit"])
    assert {k: entry[k] for k in ("kind", "command", "acceptance")} == {
        "kind": "unit",
        "command": spec("unit", [0])["command"],
        "acceptance": [0],
    }


def test_a_contract_obligation_sits_at_the_depth_of_its_deepest_verifier() -> None:
    specs = _pool(["unit", "integration"])
    both = {"required_verifiers": [s["digest"] for s in specs]}
    only_unit = {"required_verifiers": [specs[0]["digest"]]}
    assert planner.contract_level(both, specs) == 2
    assert planner.contract_level(only_unit, specs) == 1
    assert planner.contract_level({"required_verifiers": ["unknown"]}, specs) == 1


def test_a_contract_route_is_described_completely(repository: Any) -> None:
    task_id, _ = claimed(repository)
    task = repository.store.get(task_id, "task")
    known = registry.Registry()
    compiled = compiler.compile_obligations(repository, task, known, phase="INITIAL")
    (routed,) = planner.plan(task, compiled["obligations"], known)
    assert routed["plan"] == {
        "level": 1,
        "selected": routed["required_verifiers"],
        "covered": ["unit"],
        "route": "verifiers the task contract bound to this acceptance criterion",
        "human_required": False,
        "unsatisfiable": [],
        "deterministic_available": ["unit"],
    }
    assert routed["level"] == 1


# --- the resolver ----------------------------------------------------------------------


def test_legacy_evidence_does_not_speak_for_a_different_criterion() -> None:
    obligation = {
        "id": "PO-1",
        "derivation": "CONTRACT",
        "origin": {"acceptance_ids": [0]},
    }
    assert resolver.matches({"obligation_ids": [], "acceptance": [1]}, obligation) is False
    assert resolver.matches({"obligation_ids": [], "acceptance": [0, 1]}, obligation) is True


def test_the_task_wide_binding_is_not_read_when_every_record_carries_its_own(
    repository: Any,
) -> None:
    task_id, session = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    task = repository.store.get(task_id, "task")
    calls: list[str] = []

    with pytest.MonkeyPatch.context() as monkeypatch:
        from agentic_discipline.control import verification

        real = verification.binding
        monkeypatch.setattr(
            verification, "binding", lambda plane, task: calls.append("read") or real(plane, task)
        )
        assert [r["status"] for r in resolver.resolve_all(repository, task)] == ["VERIFIED"]

    assert calls == []


def test_the_obligation_binding_names_every_input_a_claim_depends_on(repository: Any) -> None:
    task_id, _ = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    obligation = obligations_for(repository, task_id)[0]
    task = repository.store.get(task_id, "task")
    bound = resolver.obligation_binding(repository, task, obligation)
    assert sorted(bound) == [
        "acceptance",
        "claim",
        "files",
        "policy",
        "protected_files",
        "requirements",
        "verifiers",
    ]
    assert bound["requirements"] == {}


@pytest.mark.parametrize(
    ("commands", "status", "reason"),
    [
        ([["run"]], "UNRESOLVED", "required evidence has not been produced yet"),
    ],
)
def test_an_unrun_claim_gives_its_reason(
    repository: Any, commands: list[list[str]], status: str, reason: str
) -> None:
    del commands
    task_id, _ = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    (resolution,) = resolver.resolve_all(repository, repository.store.get(task_id, "task"))
    assert (resolution["status"], resolution["reason"]) == (status, reason)
    assert resolution["superseded"] == []
    assert len(resolution["binding_digest"]) == 64


@pytest.mark.parametrize(
    ("verification", "status", "reason"),
    [
        ([spec("unit", [0])], "VERIFIED", "every required verifier has current passing evidence"),
        ([spec("unit", [0], FAILS)], "FAILED", "current evidence refutes this claim"),
        (
            [spec("unit", [0]), spec("acceptance", [0], FAILS)],
            "CONFLICTED",
            "current evidence both supports and refutes this claim",
        ),
        (
            [spec("unit", [0], ["no-such-verifier-binary"])],
            "BLOCKED",
            "a required verifier could not run to a verdict",
        ),
    ],
)
def test_each_resolved_state_gives_its_reason(
    repository: Any, verification: list[dict[str, Any]], status: str, reason: str
) -> None:
    task_id, session = claimed(
        repository, contract(acceptance=["The value is one"], verification=verification)
    )
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    (resolution,) = resolver.resolve_all(repository, repository.store.get(task_id, "task"))
    assert (resolution["status"], resolution["reason"]) == (status, reason)


def test_a_stale_claim_gives_its_reason(repository: Any) -> None:
    task_id, session = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    (repository.root / "src" / "report.py").write_text("value = 2\n", encoding="utf-8")
    (resolution,) = resolver.resolve_all(repository, repository.store.get(task_id, "task"))
    assert (resolution["status"], resolution["reason"]) == (
        "STALE",
        "the evidence for this claim no longer matches current inputs",
    )


def test_an_unknown_verdict_and_a_missing_route_give_their_reasons() -> None:
    base = {
        "id": "PO-1",
        "status": "UNRESOLVED",
        "claim": "c",
        "derivation": "POLICY",
        "origin": {"requirement_ids": [], "acceptance_ids": []},
        "affected_paths": ["src"],
        "plan": {"deterministic_available": [], "human_required": False},
    }
    record = {
        "id": "E1",
        "verifier": "V",
        "result": "UNKNOWN",
        "acceptance": [],
        "obligation_ids": ["PO-1"],
        "obligation_bindings": {"PO-1": {"files": {}}},
        "binding": {},
        "run_consistent": True,
    }
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(resolver, "artifact_intact", lambda plane, evidence: True)
        monkeypatch.setattr(resolver, "outcome_matches", lambda plane, evidence: True)
        monkeypatch.setattr(resolver, "obligation_binding", lambda p, t, o: {"files": {}})
        unknown = resolver.resolve(
            object(),
            {"id": "T"},
            {**base, "required_verifiers": ["V"]},
            evidence=[record],
            task_binding={},
        )
        routeless = resolver.resolve(
            object(), {"id": "T"}, {**base, "required_verifiers": []}, evidence=[], task_binding={}
        )
        described = resolver.resolve(
            object(),
            {"id": "T"},
            {**base, "required_verifiers": [], "plan": {**base["plan"], "route": "because"}},
            evidence=[],
            task_binding={},
        )
    assert (unknown["status"], unknown["reason"]) == (
        "UNKNOWN",
        "a required verifier returned no verdict",
    )
    assert (routeless["status"], routeless["reason"]) == (
        "UNKNOWN",
        "no verifier is selected for this claim",
    )
    assert described["reason"] == "because"


def test_a_waived_claim_resolves_to_a_complete_record(repository: Any) -> None:
    task_id, _ = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    obligation = obligations_for(repository, task_id)[0]
    service.waive(repository, obligation["id"], "accepted", "owner")
    stored = repository.store.get(obligation["id"], "obligation")
    assert resolver.resolve(
        repository,
        repository.store.get(task_id, "task"),
        stored,
        evidence=resolver.task_evidence(repository, task_id),
    ) == {
        "obligation_id": obligation["id"],
        "status": "WAIVED",
        "reason": "an owner waiver is recorded for this obligation",
        "current": [],
        "stale": [],
        "superseded": [],
        "missing_verifiers": [],
    }


def test_the_debt_report_counts_verified_and_waived_claims(repository: Any) -> None:
    task_id, session = claimed(
        repository,
        contract(
            acceptance=["The value is one", "It renders"],
            verification=[spec("unit", [0]), spec("acceptance", [1])],
        ),
    )
    service.compile_plan(repository, task_id, phase="INITIAL")
    first, second = sorted(obligations_for(repository, task_id), key=lambda o: o["claim"])
    service.waive(repository, first["id"], "accepted", "owner")
    service.verify(repository, task_id, session)

    report = resolver.debt(repository, repository.store.get(task_id, "task"))

    assert (report["obligations"], report["required"]) == (2, 2)
    assert (report["verified"], report["waived"], report["proof_debt"]) == (1, 1, 0)
    assert report["required_counts"] == {"VERIFIED": 1, "WAIVED": 1}
    del second


# --- the decision ----------------------------------------------------------------------


def test_the_decisions_are_the_declared_ones() -> None:
    assert decision.DECISIONS == (
        "COMPLETE",
        "BLOCK",
        "ESCALATE",
        "HUMAN_REQUIRED",
        "REPAIR",
        "EXPAND_VERIFICATION",
        "CONTINUE",
    )


def _decided(repository: Any, verification: list[dict[str, Any]], **extra: Any) -> Any:
    task_id, session = claimed(
        repository, contract(acceptance=["The value is one"], verification=verification, **extra)
    )
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    task = repository.store.get(task_id, "task")
    obligation = obligations_for(repository, task_id)[0]
    return decision.decide(repository, task, resolver.debt(repository, task)), task, obligation


def test_a_complete_decision_is_described_completely(repository: Any) -> None:
    decided, task, _ = _decided(repository, [spec("unit", [0])])
    assert decided == {
        "task_id": task["id"],
        "decision": "COMPLETE",
        "reasons": ["every mandatory obligation is resolved by current evidence"],
        "proof_debt": 0,
        "risk": "LOW",
        "required_counts": {"VERIFIED": 1},
        "completion_allowed": True,
        "next_actions": [],
    }


def test_a_conflict_decision_names_the_claim_and_what_to_do(repository: Any) -> None:
    decided, _, obligation = _decided(
        repository, [spec("unit", [0]), spec("acceptance", [0], FAILS)]
    )
    assert decided["decision"] == "BLOCK"
    assert decided["reasons"] == [f"conflicting evidence on {obligation['id']}: The value is one"]
    assert decided["next_actions"] == [
        f"Reconcile the contradictory evidence on {obligation['id']} before continuing."
    ]


def test_a_repair_decision_names_the_claim(repository: Any) -> None:
    decided, _, obligation = _decided(repository, [spec("unit", [0], FAILS)])
    assert decided["reasons"] == [
        f"{obligation['id']} failed inside the task contract: The value is one"
    ]


def test_a_blocked_verifier_escalates_with_its_reason(repository: Any) -> None:
    decided, _, obligation = _decided(repository, [spec("unit", [0], ["no-such-verifier-binary"])])
    assert decided["decision"] == "ESCALATE"
    assert decided["reasons"] == [
        f"{obligation['id']} is BLOCKED: a required verifier could not run to a verdict"
    ]


def test_an_unknown_claim_of_low_criticality_does_not_escalate_by_itself(
    repository: Any,
) -> None:
    """Only a severe unknown escalates straight away; a lesser one asks for its route."""
    task_id, session = claimed(repository, contract(scope=["src", "deploy"]))
    sources(repository.root, {"deploy/pipeline.yml": "steps: []\n"})
    service.reconcile(repository, task_id)
    task = repository.store.get(task_id, "task")
    report = resolver.debt(repository, task)
    assert sorted(report["required_counts"]) == ["UNKNOWN", "UNRESOLVED"]

    decided = decision.decide(repository, task, report)

    assert decided["decision"] == "EXPAND_VERIFICATION"
    del session


def test_the_next_actions_for_each_state_are_specific() -> None:
    obligations = {
        "PO-S": {"claim": "s", "acceptable_proof_capabilities": ["unit"]},
        "PO-H": {"claim": "Humans agree", "acceptable_proof_capabilities": ["human_judgment"]},
        "PO-U": {"claim": "u", "acceptable_proof_capabilities": []},
        "PO-K": {"claim": "k", "acceptable_proof_capabilities": ["migration_safety", "unit"]},
    }
    outstanding = [
        {"obligation_id": "PO-S", "status": "STALE"},
        {"obligation_id": "PO-H", "status": "HUMAN_REQUIRED"},
        {"obligation_id": "PO-U", "status": "UNKNOWN"},
        {"obligation_id": "PO-K", "status": "UNKNOWN"},
    ]
    assert decision._next_actions(outstanding, obligations) == [
        "Ask a human to settle PO-H: Humans agree",
        "Run the verifier for PO-S and record evidence.",
        "Declare a verifier that can supply migration_safety, unit for PO-K, or record an "
        "owner waiver.",
        "Declare a verifier that can supply this capability for PO-U, or record an owner waiver.",
    ]


def test_a_human_required_decision_names_the_claim(repository: Any) -> None:
    task_id, session = claimed(
        repository,
        contract(verification=[spec("unit", [0]), spec("mutation", [])], risk="CRITICAL"),
    )
    (repository.root / "src" / "report.py").write_text("value = 1  # revised\n")
    service.reconcile(repository, task_id)
    service.verify(repository, task_id, session)
    task = repository.store.get(task_id, "task")
    accepted = next(
        o
        for o in obligations_for(repository, task_id)
        if "HUMAN-ACCEPTANCE" in o["origin"]["policy_ids"]
    )

    decided = decision.decide(repository, task, resolver.debt(repository, task))

    assert decided["reasons"] == [
        f"{accepted['id']} needs human judgment: A human explicitly accepted this critical change."
    ]


def test_an_expand_decision_names_why_each_claim_needs_a_run(repository: Any) -> None:
    task_id, _ = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    task = repository.store.get(task_id, "task")
    obligation = obligations_for(repository, task_id)[0]
    decided = decision.decide(repository, task, resolver.debt(repository, task))
    assert decided["reasons"] == [
        f"{obligation['id']} needs a verifier run: required evidence has not been produced yet"
    ]


# --- the service's reports ---------------------------------------------------------------


def test_the_task_report_is_described_completely(repository: Any) -> None:
    task_id, session = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    obligation = obligations_for(repository, task_id)[0]

    report = service.status(repository, task_id)

    assert report["totals"] == {"required": 1, "proof_debt": 0, "blocked_completion": []}
    assert (
        report["meaning"] == "required obligations are mandatory and confirmed by the actual change"
    )
    (task,) = report["tasks"]
    assert {k: v for k, v in task.items() if k != "decision"} == {
        "task_id": task_id,
        "objective": "Keep the reported value at one",
        "state": "VERIFYING",
        "risk": "LOW",
        "obligations": [
            {
                "id": obligation["id"],
                "claim": "The reported value is one",
                "criticality": "LOW",
                "mandatory": True,
                "enforced": True,
                "derivation": "CONTRACT",
                "level": 1,
                "capabilities": ["unit"],
                "status": "VERIFIED",
            }
        ],
        "required": 1,
        "counts": {"VERIFIED": 1},
        "proof_debt": 0,
    }


def test_the_project_status_leaves_out_cancelled_and_superseded_tasks(repository: Any) -> None:
    active, _ = claimed(repository)
    service.compile_plan(repository, active, phase="INITIAL")
    repository.release(active, _)
    cancelled, session = claimed(repository, contract(objective="Retired work"))
    service.compile_plan(repository, cancelled, phase="INITIAL")
    repository.release(cancelled, session)
    repository.transition(cancelled, "CANCELLED", "no longer needed")

    assert [t["task_id"] for t in service.status(repository)["tasks"]] == [active]
    assert service.status(repository)["totals"]["blocked_completion"] == [active]


def test_the_plan_view_is_described_completely(repository: Any) -> None:
    task_id, _ = claimed(repository)
    first = service.compile_plan(repository, task_id, phase="INITIAL")
    sources(repository.root, {"src/auth/login.py": "def login():\n    return True\n"})
    latest = service.reconcile(repository, task_id)
    stored = {o["id"]: o for o in obligations_for(repository, task_id)}

    view = service.plan_view(repository, task_id)

    assert view == {
        "task_id": task_id,
        "initial": {
            "phase": "INITIAL",
            "obligations": 1,
            "plan_digest": first["plan_digest"],
        },
        "current": {
            "phase": "RECONCILED",
            "obligations": 2,
            "plan_digest": latest["plan_digest"],
            "signals": ["auth"],
            "observed_paths": ["src/auth/login.py"],
            "impact": latest["impact"],
        },
        "expanded_by": latest["expansion"]["added"],
        "revisions": 2,
        "routes": {
            i: {
                "claim": o["claim"],
                "level": o["level"],
                "route": o["plan"]["route"],
                "verifiers": o["required_verifiers"],
            }
            for i, o in sorted(stored.items())
        },
    }


def test_a_compilation_is_recorded_and_audited_completely(repository: Any) -> None:
    task_id, _ = claimed(repository)
    plan = service.compile_plan(repository, task_id, phase="INITIAL")
    obligation = obligations_for(repository, task_id)[0]

    assert plan["added"] == [obligation["id"]]
    assert (plan["widened"], plan["retained"], plan["refused_contractions"]) == ([], [], [])
    assert plan["expansion"] == {
        "added": [obligation["id"]],
        "widened": [],
        "retained": [],
        "reason": "obligations only widen; a recorded obligation is never dropped by a recompile",
    }
    event = next(e for e in repository.store.timeline() if e["action"] == "assurance.compile")
    assert (event["actor"], event["payload"]) == (
        "local",
        {
            "task_id": task_id,
            "phase": "INITIAL",
            "added": [obligation["id"]],
            "widened": [],
            "retained": [],
            "refused_contractions": [],
        },
    )
    assert obligation["created_at"] == obligation["updated_at"]
    assert obligation["waiver_id"] is None


def test_an_identical_recompile_writes_nothing_and_a_widening_one_is_named(
    repository: Any,
) -> None:
    task_id, _ = claimed(repository, contract(risk="STANDARD"))
    sources(repository.root, {"src/auth/login.py": "def login():\n    return True\n"})
    service.reconcile(repository, task_id)
    authorization = next(
        o for o in obligations_for(repository, task_id) if "SEC-AUTHZ" in o["origin"]["policy_ids"]
    )

    again = service.reconcile(repository, task_id)
    assert again["widened"] == []
    assert (
        repository.store.get(authorization["id"], "obligation")["version"]
        == authorization["version"]
    )

    sources(repository.root, {"src/auth/session.py": "def check():\n    return True\n"})
    widened = service.reconcile(repository, task_id)

    assert authorization["id"] in widened["widened"]
    stored = repository.store.get(authorization["id"], "obligation")
    assert stored["affected_paths"] == ["src/auth/login.py", "src/auth/session.py"]
    assert stored["updated_at"] > authorization["updated_at"]


def test_escalation_skips_what_it_must_and_raises_the_rest(repository: Any) -> None:
    task_id, _ = claimed(repository, contract(risk="HIGH"))
    service.reconcile(repository, task_id)
    contract_claim, strength = sorted(
        obligations_for(repository, task_id), key=lambda o: o["derivation"]
    )
    outstanding = [
        {"obligation_id": contract_claim["id"], "status": "UNKNOWN"},
        {"obligation_id": strength["id"], "status": "FAILED"},
        {"obligation_id": strength["id"], "status": "UNKNOWN"},
    ]
    before = [e for e in repository.store.timeline() if e["action"] == "assurance.escalate"]

    assert service.escalate(repository, task_id, outstanding) == [strength["id"]]
    assert repository.store.get(strength["id"], "obligation")["floor"] == 2
    events = [e for e in repository.store.timeline() if e["action"] == "assurance.escalate"]
    assert len(events) - len(before) == 1
    assert events[0]["payload"] == {"task_id": task_id, "obligations": [strength["id"]]}

    assert service.escalate(repository, task_id, outstanding[:2]) == []
    assert [e for e in repository.store.timeline() if e["action"] == "assurance.escalate"] == events


def test_one_verify_call_raises_a_claim_one_level_when_nothing_deeper_can_run(
    repository: Any,
) -> None:
    task_id, session = claimed(repository, contract(risk="HIGH"))
    service.compile_plan(repository, task_id, phase="INITIAL")

    outcome = service.verify(repository, task_id, session)

    strength = next(
        o
        for o in obligations_for(repository, task_id)
        if "TEST-STRENGTH" in o["origin"]["policy_ids"]
    )
    assert outcome["escalated"] == [strength["id"]]
    assert strength["floor"] == 2


def test_a_verify_result_is_described_completely(repository: Any) -> None:
    task_id, session = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    outcome = service.verify(repository, task_id, session)
    task = repository.store.get(task_id, "task")
    assert sorted(outcome) == [
        "debt",
        "decision",
        "escalated",
        "executions",
        "plan",
        "status",
        "task_id",
    ]
    assert outcome["task_id"] == task_id
    assert outcome["debt"] == resolver.debt(repository, task)
    assert (
        outcome["plan"]["id"]
        == max(repository.store.list("assurance_plan"), key=lambda p: p["created_at"])["id"]
    )


def test_an_obligation_explanation_is_described_completely(repository: Any) -> None:
    requirement = _requirement(repository, "FR-1 reporting")
    task_id, session = claimed(repository, contract(requirements=[requirement["id"]]))
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    obligation = obligations_for(repository, task_id)[0]
    (record,) = repository.store.list("evidence")

    explained = service.explain(repository, obligation["id"])

    assert {k: v for k, v in explained.items() if k != "obligation"} == {
        "task_id": task_id,
        "claim": "The reported value is one",
        "origin": {
            **obligation["origin"],
            "requirements": [
                {"id": requirement["id"], "name": "FR-1 reporting", "authority": "contract"}
            ],
            "acceptance": ["The reported value is one"],
        },
        "required_because": "acceptance criterion declared in the task contract",
        "affected_paths": ["src"],
        "affected_symbols": [],
        "plan": obligation["plan"],
        "status": "VERIFIED",
        "reason": "every required verifier has current passing evidence",
        "evidence": [
            {
                "id": record["id"],
                "kind": "unit",
                "result": "PASS",
                "evidence_class": "DETERMINISTIC",
                "command": record["command"],
                "exit_code": 0,
                "currency": "CURRENT",
            }
        ],
        "missing_verifiers": [],
        "waiver": None,
        "human_request": None,
    }


def test_a_record_with_no_class_is_explained_as_measured(repository: Any) -> None:
    task_id, session = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    (record,) = repository.store.list("evidence")
    with repository.store.transaction():
        repository.store.put(
            "evidence",
            {k: v for k, v in record.items() if k != "evidence_class"},
            expected=record["version"],
        )
    obligation = obligations_for(repository, task_id)[0]
    assert (
        service.explain(repository, obligation["id"])["evidence"][0]["evidence_class"] == "MEASURED"
    )


def test_explanations_group_evidence_by_currency(repository: Any) -> None:
    task_id, session = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    (repository.root / "src" / "report.py").write_text("value = 2\n", encoding="utf-8")
    service.verify(repository, task_id, session)
    obligation = obligations_for(repository, task_id)[0]

    currencies = [e["currency"] for e in service.explain(repository, obligation["id"])["evidence"]]

    assert currencies == ["CURRENT", "STALE"]


def test_a_task_explanation_carries_each_open_claim_completely(repository: Any) -> None:
    task_id, session = claimed(repository, contract(verification=[spec("unit", [0], FAILS)]))
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    obligation = obligations_for(repository, task_id)[0]
    (record,) = repository.store.list("evidence")

    explained = service.explain(repository, task_id)

    assert {k: explained[k] for k in ("task_id", "objective", "state", "decision")} == {
        "task_id": task_id,
        "objective": "Keep the reported value at one",
        "state": "FAILED",
        "decision": "REPAIR",
    }
    assert explained["outstanding"] == [
        {
            "obligation_id": obligation["id"],
            "status": "FAILED",
            "claim": "The reported value is one",
            "criticality": "LOW",
            "reason": "current evidence refutes this claim",
            "current_evidence": [record["id"]],
            "stale_evidence": [],
            "missing_verifiers": [record["verifier"]],
            "origin": "acceptance criterion declared in the task contract",
        }
    ]


def test_a_human_request_is_described_completely_and_leaves_human_verdicts_out(
    repository: Any,
) -> None:
    task_id, session = claimed(
        repository,
        contract(verification=[spec("unit", [0]), spec("mutation", [])], risk="CRITICAL"),
    )
    (repository.root / "src" / "report.py").write_text("value = 1  # revised\n")
    service.reconcile(repository, task_id)
    service.verify(repository, task_id, session)
    accepted = next(
        o
        for o in obligations_for(repository, task_id)
        if "HUMAN-ACCEPTANCE" in o["origin"]["policy_ids"]
    )
    task = repository.store.get(task_id, "task")
    request = service.human_request(repository, task, accepted, {"status": "HUMAN_REQUIRED"})

    assert request == {
        "obligation_id": accepted["id"],
        "claim": "A human explicitly accepted this critical change.",
        "inspect": ["src/report.py"],
        "reference": ["value API"],
        "automatic_checks_passed": ["mutation", "unit"],
        "remaining_judgment": "CRITICAL risk requires a recorded human acceptance of src/report.py",
        "why_no_verifier": "human resolution; no automated verifier can settle this claim",
        "resolve_with": f"agentic assurance resolve {accepted['id']} --decision <text>",
        "current_status": "HUMAN_REQUIRED",
    }

    service.resolve_human(repository, accepted["id"], "accepted")
    after = service.human_request(repository, task, accepted, {"status": "VERIFIED"})
    assert after["automatic_checks_passed"] == ["mutation", "unit"]


def test_a_failed_check_is_not_listed_as_already_passed(repository: Any) -> None:
    task_id, session = claimed(
        repository,
        contract(verification=[spec("unit", [0]), spec("mutation", [], FAILS)], risk="CRITICAL"),
    )
    (repository.root / "src" / "report.py").write_text("value = 1  # revised\n")
    service.reconcile(repository, task_id)
    service.verify(repository, task_id, session)
    accepted = next(
        o
        for o in obligations_for(repository, task_id)
        if "HUMAN-ACCEPTANCE" in o["origin"]["policy_ids"]
    )
    task = repository.store.get(task_id, "task")
    assert service.human_request(repository, task, accepted, {"status": "X"})[
        "automatic_checks_passed"
    ] == ["unit"]


def test_a_human_verdict_is_recorded_completely(repository: Any) -> None:
    task_id, _ = claimed(
        repository,
        contract(verification=[spec("unit", [0]), spec("mutation", [])], risk="CRITICAL"),
    )
    (repository.root / "src" / "report.py").write_text("value = 1  # revised\n")
    service.reconcile(repository, task_id)
    accepted = next(
        o
        for o in obligations_for(repository, task_id)
        if "HUMAN-ACCEPTANCE" in o["origin"]["policy_ids"]
    )

    result = service.resolve_human(repository, accepted["id"], "The owner accepted it")

    record = result["evidence"]
    artifact = repository.directory / "evidence" / f"{record['id']}.json"
    written = json.loads(artifact.read_text(encoding="utf-8"))
    assert {k: v for k, v in written.items() if k != "recorded_at"} == {
        "tool": "human",
        "obligation_id": accepted["id"],
        "claim": accepted["claim"],
        "decision": "The owner accepted it",
        "accepted": True,
        "inspected": ["src/report.py"],
        "result": "PASS",
        "exit_code": 0,
    }
    assert {
        k: record[k]
        for k in (
            "task_id",
            "kind",
            "verifier",
            "acceptance",
            "run_id",
            "result",
            "exit_code",
            "command",
            "evidence_class",
            "judgment",
            "obligation_ids",
            "artifact_ref",
            "run_consistent",
            "stale",
        )
    } == {
        "task_id": task_id,
        "kind": "human",
        "verifier": f"human:{accepted['id']}",
        "acceptance": [],
        "run_id": record["id"],
        "result": "PASS",
        "exit_code": 0,
        "command": [],
        "evidence_class": "HUMAN",
        "judgment": "ACCEPTED",
        "obligation_ids": [accepted["id"]],
        "artifact_ref": f".agentic/control/evidence/{record['id']}.json",
        "run_consistent": True,
        "stale": False,
    }
    assert record["started_at"] == record["finished_at"] == written["recorded_at"]
    assert record["knowledge_version"] == repository.store.knowledge_version
    assert set(record["obligation_bindings"]) == {accepted["id"]}
    (decided,) = [d for d in repository.store.list("decision") if d.get("obligation_id")]
    assert {k: v for k, v in decided.items() if k not in {"id", "version"}} == {
        "obligation_id": accepted["id"],
        "task_id": task_id,
        "question": accepted["claim"],
        "decision": "The owner accepted it",
        "state": "DECIDED",
        "authority": "human",
    }
    assert result["obligation"] == repository.store.get(accepted["id"], "obligation")


def test_a_human_verdict_without_a_decision_is_refused(repository: Any) -> None:
    with pytest.raises(ControlError) as caught:
        service.resolve_human(repository, "PO-anything", "   ")
    assert (caught.value.code, str(caught.value)) == (
        "DECISION_REQUIRED",
        "Record what the human decided",
    )


def test_a_waiver_is_recorded_and_audited_completely(repository: Any) -> None:
    task_id, _ = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    obligation = obligations_for(repository, task_id)[0]

    result = service.waive(repository, obligation["id"], "accepted for the spike", "owner")

    waiver = result["waiver"]
    assert {k: v for k, v in waiver.items() if k not in {"id", "version", "created_at"}} == {
        "obligation_id": obligation["id"],
        "task_id": task_id,
        "claim": "The reported value is one",
        "criticality": "LOW",
        "reason": "accepted for the spike",
        "authorization": "owner",
        "status_when_waived": "UNRESOLVED",
    }
    assert result["obligation"]["waiver_id"] == waiver["id"]
    assert result["obligation"]["updated_at"] >= obligation["updated_at"]
    event = next(e for e in repository.store.timeline() if e["action"] == "assurance.waive")
    assert (event["actor"], event["payload"]) == (
        "local-owner",
        {
            "obligation_id": obligation["id"],
            "criticality": "LOW",
            "reason": "accepted for the spike",
            "authorization": "owner",
        },
    )
    writes = [
        e
        for e in repository.store.timeline()
        if e["action"] in {"waiver.write", "obligation.write"} and e["actor"] == "local-owner"
    ]
    assert len(writes) == 2


@pytest.mark.parametrize("status", ["FAILED", "CONFLICTED"])
def test_a_waiver_is_refused_over_every_refuting_state(repository: Any, status: str) -> None:
    verification = (
        [spec("unit", [0], FAILS)]
        if status == "FAILED"
        else [spec("unit", [0]), spec("acceptance", [0], FAILS)]
    )
    task_id, session = claimed(
        repository, contract(acceptance=["The value is one"], verification=verification)
    )
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    obligation = obligations_for(repository, task_id)[0]
    with pytest.raises(ControlError) as caught:
        service.waive(repository, obligation["id"], "no", "owner")
    assert caught.value.code == "EVIDENCE_REFUTES_CLAIM"


# --- integrity -------------------------------------------------------------------------


def test_the_integrity_report_is_described_completely(repository: Any) -> None:
    task_id, _ = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    assert service.integrity(repository) == {
        "status": "PASS",
        "findings": [],
        "obligations": 1,
        "waivers": 0,
        "checked": [
            "obligation status is an owner state",
            "no obligation a plan recorded has disappeared",
            "every waiver records a reason and its authority",
            "no completed task holds mandatory proof debt",
            "judgment evidence never claims a deterministic class",
            "evidence references the run that produced it",
        ],
    }


def test_the_integrity_findings_name_what_they_are_about(repository: Any) -> None:
    task_id, session = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    obligation = obligations_for(repository, task_id)[0]
    (record,) = repository.store.list("evidence")
    with repository.store.transaction():
        repository.store.put(
            "obligation", {**obligation, "status": "WAIVED"}, expected=obligation["version"]
        )
        repository.store.put(
            "evidence",
            {**record, "judgment": "NO_COUNTEREXAMPLE_FOUND", "run_id": ""},
            expected=record["version"],
        )

    findings = service.integrity(repository)["findings"]

    assert findings == [
        {"obligation_id": obligation["id"], "finding": "waived without a recorded waiver"},
        {"evidence_id": record["id"], "finding": "judgment evidence declared as deterministic"},
        {
            "evidence_id": record["id"],
            "finding": "evidence does not reference the execution that created it",
        },
    ]


def test_integrity_reads_every_task_even_after_one_it_cannot_read(repository: Any) -> None:
    """A task with no plan, and a task whose state cannot be read, do not hide a later one."""
    empty, first_session = claimed(repository)
    repository.release(empty, first_session)
    unreadable, second_session = claimed(repository, contract(objective="Unreadable"))
    service.compile_plan(repository, unreadable, phase="INITIAL")
    repository.release(unreadable, second_session)
    completed, session = claimed(repository, contract(objective="Completed and then moved"))
    service.compile_plan(repository, completed, phase="INITIAL")
    service.verify(repository, completed, session)
    repository.checkpoint(completed, session, checkpoint())
    complete(repository, completed, session)
    (repository.root / "src" / "report.py").write_text("value = 2\n", encoding="utf-8")
    real = service.resolve_all

    def failing_for(plane: Any, task: dict[str, Any]) -> Any:
        if task["id"] == unreadable:
            raise OSError("unreadable")
        return real(plane, task)

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(service, "resolve_all", failing_for)
        report = service.integrity(repository)

    assert [f.get("task_id") for f in report["findings"]] == [completed]


def test_an_open_forecast_does_not_count_against_a_completed_task(repository: Any) -> None:
    task_id, session = claimed(repository, contract(scope=["src"]))
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    repository.checkpoint(task_id, session, checkpoint())
    complete(repository, task_id, session)
    forecast = {
        **obligations_for(repository, task_id)[0],
    }
    # A second, unenforced claim, as a forecast would record it.
    with repository.store.transaction():
        repository.store.put(
            "obligation",
            {
                **forecast,
                "id": model.obligation_id(task_id, "policy:SEC-AUTHZ"),
                "derivation": "POLICY",
                "enforced": False,
                "required_verifiers": [],
                "origin": {**forecast["origin"], "acceptance_ids": [], "policy_ids": ["SEC-AUTHZ"]},
            },
        )

    assert service.integrity(repository)["status"] == "PASS"


# --- migration -------------------------------------------------------------------------


def test_the_migration_plan_is_described_completely(repository: Any) -> None:
    task_id, _ = claimed(repository)
    _two_point_zero(repository)
    assert migration.plan(repository) == {
        "dry_run": True,
        "from_schema": "1",
        "to_schema": "2",
        "tasks": [task_id],
        "acceptance_criteria": 1,
        "evidence_records": 0,
        "already_migrated": False,
        "becomes": [
            "each acceptance criterion becomes a mandatory proof obligation",
            "policy obligations from the declared scope are recorded but not enforced until"
            " the actual change confirms them",
            "existing evidence keeps its artefacts and gains legacy assurance provenance",
            "completion starts refusing a task that holds mandatory proof debt",
        ],
        "unreconstructible": [
            "which obligation a legacy evidence record was produced for, beyond its"
            " acceptance criterion index"
        ],
        "writes": ["knowledge database", "backup file when --backup is given"],
    }


def test_a_migration_is_recorded_and_audited_completely(repository: Any) -> None:
    task_id, session = claimed(repository)
    from agentic_discipline.control.verification import verify as run

    run(repository, task_id, session)
    _two_point_zero(repository)

    result = migration.migrate(repository)

    record = repository.store.get(result["migration_id"], "assurance_migration")
    (evidence,) = repository.store.list("evidence")
    assert {k: v for k, v in record.items() if k not in {"id", "version", "created_at"}} == {
        "from_schema": "1",
        "to_schema": "2",
        "status": "APPLIED",
        "tasks": [task_id],
        "obligations": [obligations_for(repository, task_id)[0]["id"]],
        "reclassified_evidence": [evidence["id"]],
        "reactivated": [],
    }
    assert result == {
        "migrated": True,
        "from_schema": "1",
        "to_schema": "2",
        "migration_id": record["id"],
        "obligations": 1,
        "tasks": [task_id],
        "reclassified_evidence": 1,
        "legacy_provenance": "evidence keeps its artefacts; its obligation link is the"
        " acceptance criterion it was recorded against, and nothing more",
    }
    event = next(e for e in repository.store.timeline() if e["action"] == "assurance.migrate")
    assert (event["actor"], event["payload"]) == (
        "local-owner",
        {"from": "1", "to": "2", "evidence": 1},
    )


def test_migration_classifies_every_unclassified_record_and_keeps_a_recorded_class(
    repository: Any,
) -> None:
    first, session = claimed(
        repository, contract(verification=[spec("unit", [0]), spec("bespoke", [])])
    )
    from agentic_discipline.control.verification import verify as run

    run(repository, first, session)
    unit, bespoke = sorted(repository.store.list("evidence"), key=lambda e: e["kind"])[::-1]
    with repository.store.transaction():
        repository.store.put(
            "evidence",
            {**bespoke, "assurance_provenance": "LEGACY"},
            expected=bespoke["version"],
        )
        repository.store.put(
            "evidence", {**unit, "evidence_class": "MEASURED"}, expected=unit["version"]
        )
    _two_point_zero(repository)

    result = migration.migrate(repository)

    assert result["reclassified_evidence"] == 1
    reclassified = repository.store.get(unit["id"], "evidence")
    assert (reclassified["evidence_class"], reclassified["assurance_provenance"]) == (
        "MEASURED",
        "LEGACY",
    )


def test_an_undeclared_legacy_kind_is_classified_as_measured(repository: Any) -> None:
    task_id, session = claimed(repository, contract(verification=[spec("bespoke", [0])]))
    from agentic_discipline.control.verification import verify as run

    run(repository, task_id, session)
    (record,) = repository.store.list("evidence")
    with repository.store.transaction():
        repository.store.put(
            "evidence",
            {k: v for k, v in record.items() if k != "evidence_class"},
            expected=record["version"],
        )
    _two_point_zero(repository)

    migration.migrate(repository)

    assert repository.store.get(record["id"], "evidence")["evidence_class"] == "MEASURED"


def test_a_rollback_is_recorded_and_audited_completely(repository: Any) -> None:
    task_id, _ = claimed(repository)
    _two_point_zero(repository)
    applied = migration.migrate(repository)
    obligation = obligations_for(repository, task_id)[0]

    result = migration.rollback(repository, applied["migration_id"], "reverting")

    assert {k: v for k, v in result.items() if k != "migration"} == {
        "rolled_back": True,
        "schema_version": "1",
        "obligations_retired": 1,
        "preserved": "obligations, plans, waivers and evidence remain readable for audit",
    }
    assert (result["migration"]["status"], result["migration"]["rollback_reason"]) == (
        "ROLLED_BACK",
        "reverting",
    )
    reverted = repository.store.get(obligation["id"], "obligation")
    assert reverted["reverted"] is True
    assert reverted["updated_at"] >= obligation["updated_at"]
    event = next(e for e in repository.store.timeline() if e["action"] == "assurance.rollback")
    assert (event["actor"], event["payload"]) == (
        "local-owner",
        {
            "migration": applied["migration_id"],
            "reason": "reverting",
            "obligations": [obligation["id"]],
        },
    )


def test_reactivation_is_recorded_and_owned(repository: Any) -> None:
    task_id, _ = claimed(repository)
    _two_point_zero(repository)
    applied = migration.migrate(repository)
    migration.rollback(repository, applied["migration_id"], "reverting")
    obligation = obligations_for(repository, task_id) or [
        o for o in repository.store.list("obligation") if o["task_id"] == task_id
    ]

    again = migration.migrate(repository)

    record = repository.store.get(again["migration_id"], "assurance_migration")
    assert record["reactivated"] == [obligation[0]["id"]]
    revived = repository.store.get(obligation[0]["id"], "obligation")
    assert revived["reverted"] is False
    writes = [
        e
        for e in repository.store.timeline()
        if e["action"] == "obligation.write" and e["payload"]["id"] == obligation[0]["id"]
    ]
    assert writes[0]["actor"] == "local-owner"


def test_reclassification_and_rollback_writes_are_owned(repository: Any) -> None:
    task_id, session = claimed(repository)
    from agentic_discipline.control.verification import verify as run

    run(repository, task_id, session)
    _two_point_zero(repository)
    applied = migration.migrate(repository)
    migration.rollback(repository, applied["migration_id"], "reverting")
    evidence_actors = {
        e["actor"] for e in repository.store.timeline() if e["action"] == "evidence.write"
    }
    migration_actors = {
        e["actor"]
        for e in repository.store.timeline()
        if e["action"] == "assurance_migration.write"
    }
    # The run wrote the evidence; only the owner reclassified it and recorded the migration.
    assert "local-owner" in evidence_actors
    assert migration_actors == {"local-owner"}
