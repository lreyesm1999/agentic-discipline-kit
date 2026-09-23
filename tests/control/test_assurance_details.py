"""Details the mutation campaign showed nothing else pinned.

Each case here was written against a specific surviving mutant: a set with one element no
test exercised, a loop whose order the other tests left to chance, an audit attribution
nobody read back, a record key that could be renamed without anything failing. Where the
order of records mattered, the fixture fixes it rather than relying on random identifiers.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest
from assurance_support import claimed, contract, sources, spec

from agentic_discipline.control.assurance import (
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


def _critical(repository: Any, **extra: Any) -> tuple[str, str, dict[str, Any]]:
    task_id, session = claimed(
        repository,
        contract(verification=[spec("unit", [0]), spec("mutation", [])], risk="CRITICAL", **extra),
    )
    (repository.root / "src" / "report.py").write_text("value = 1  # revised\n")
    service.reconcile(repository, task_id)
    accepted = next(
        o
        for o in obligations_for(repository, task_id)
        if "HUMAN-ACCEPTANCE" in o["origin"]["policy_ids"]
    )
    return task_id, session, accepted


# --- vocabularies that must accept everything they declare ------------------------------


def test_a_verifier_may_declare_every_known_capability() -> None:
    registry.descriptor_contract(
        {
            "id": "everything",
            "capabilities": sorted(model.CAPABILITIES),
            "evidence_class": "MEASURED",
            "cost": "low",
            "level": 1,
        }
    )


def test_an_obligation_may_accept_every_known_capability() -> None:
    model.obligation_contract(
        {
            "task_id": "T",
            "claim": "c",
            "origin": {
                "requirement_ids": [],
                "acceptance_ids": [],
                "policy_ids": [],
                "architecture_ids": [],
                "generated_reason": "why",
            },
            "derivation": "POLICY",
            "criticality": "LOW",
            "mandatory": True,
            "status": "UNRESOLVED",
            "phase": "INITIAL",
            "enforced": True,
            "acceptable_proof_capabilities": sorted(model.CAPABILITIES),
            "required_verifiers": [],
            "affected_paths": [],
            "affected_symbols": [],
            "dependencies": [],
        }
    )


def test_a_missing_obligation_field_is_an_invalid_obligation() -> None:
    with pytest.raises(ControlError) as caught:
        model.obligation_contract({})
    assert caught.value.code == "INVALID_OBLIGATION"


# --- falsification first, for each falsifying capability ---------------------------------


def _chosen(acceptable: list[str], kinds: list[str], known: Any = None) -> str:
    known = known or registry.Registry()
    task = {"verification": [spec(kind, [0]) for kind in kinds]}
    route = planner.plan_for(
        {"id": "PO-1", "acceptable_proof_capabilities": acceptable, "criticality": "LOW"},
        planner.pool(task, known),
        known,
    )
    return str(route["route"])


@pytest.mark.parametrize(
    ("acceptable", "kinds", "expected"),
    [
        (["behavioral", "invariant"], ["integration", "property"], "property supplies invariant"),
        (
            ["behavioral", "falsification"],
            ["integration", "property"],
            "property supplies falsification",
        ),
    ],
)
def test_a_falsifying_route_wins_a_tie_it_would_otherwise_lose_by_name(
    acceptable: list[str], kinds: list[str], expected: str
) -> None:
    assert _chosen(acceptable, kinds).startswith(expected)


def test_test_strength_wins_a_tie_among_equally_deep_and_costly_routes() -> None:
    """Mutation is the only built-in level-3 deterministic kind, so a peer is registered."""
    known = registry.Registry(
        [
            {
                "id": "aaa-check",
                "capabilities": ["data_preservation"],
                "evidence_class": "DETERMINISTIC",
                "cost": "high",
                "level": 3,
            }
        ]
    )
    assert _chosen(
        ["data_preservation", "test_strength"], ["aaa-check", "mutation"], known
    ).startswith("mutation supplies test_strength")


def test_a_falsifying_review_wins_a_tie_among_judgment_routes() -> None:
    known = registry.Registry(
        [
            {
                "id": "aaa-review",
                "capabilities": ["qualitative_reference_comparison"],
                "evidence_class": "AGENT_JUDGMENT",
                "cost": "high",
                "level": 3,
            }
        ]
    )
    assert _chosen(
        ["falsification_review", "qualitative_reference_comparison"],
        ["aaa-review", "adversarial"],
        known,
    ).startswith("adversarial supplies falsification_review")


def test_a_human_verifier_chosen_as_the_only_route_is_marked_human() -> None:
    task = {"verification": [spec("human", [0]), spec("unit", [0])]}
    known = registry.Registry()
    route = planner.plan_for(
        {
            "id": "PO-1",
            "acceptable_proof_capabilities": ["human_judgment", "migration_safety"],
            "criticality": "LOW",
        },
        planner.pool(task, known),
        known,
    )
    assert route["route"].startswith("human supplies human_judgment")
    assert route["human_required"] is True


# --- decisions -------------------------------------------------------------------------


def test_an_unknown_critical_claim_escalates_straight_away(repository: Any) -> None:
    task_id, session = claimed(repository, contract(scope=["src"]))
    sources(repository.root, {"src/billing/invoice.py": "total = 0\n"})
    service.reconcile(repository, task_id)
    service.verify(repository, task_id, session)
    task = repository.store.get(task_id, "task")
    report = resolver.debt(repository, task)
    money = next(
        o for o in obligations_for(repository, task_id) if "FIN-STABLE" in o["origin"]["policy_ids"]
    )
    assert money["criticality"] == "CRITICAL"

    decided = decision.decide(repository, task, report)

    assert decided["decision"] == "ESCALATE"
    assert decided["reasons"][0].startswith(f"{money['id']} is UNKNOWN: ")


def test_an_unrun_claim_is_told_to_run_its_verifier() -> None:
    assert decision._next_actions(
        [{"obligation_id": "PO-1", "status": "UNRESOLVED"}],
        {"PO-1": {"claim": "c", "acceptable_proof_capabilities": ["unit"]}},
    ) == ["Run the verifier for PO-1 and record evidence."]


# --- impact ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "scope", "expected"),
    [
        ("anything/at/all.py", ["."], True),
        ("src/a.py", ["src/"], True),
        ("src/a.py", ["src"], True),
        ("src", ["src"], True),
        ("srcx/a.py", ["src"], False),
        ("docs/a.md", ["src", "tests"], False),
    ],
)
def test_scope_membership(path: str, scope: list[str], expected: bool) -> None:
    assert impact.in_scope(path, scope) is expected


def test_a_link_the_task_began_with_and_no_longer_has_is_a_change(repository: Any) -> None:
    task = {
        "id": "TASK-x",
        "state": "CLAIMED",
        "workspace_id": None,
        "initial_files": {},
        "initial_links": {"old-link": "target"},
    }
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(impact, "fingerprint", lambda root: {})
        monkeypatch.setattr(impact, "link_fingerprint", lambda root: {})
        assert impact.changed_paths(repository, task) == ["old-link"]


def test_stale_symbols_and_stale_dependents_are_left_out(repository: Any) -> None:
    sources(repository.root, {"src/auth/login.py": "def login():\n    return True\n"})
    repository.reconcile()
    symbol = next(
        e
        for e in repository.store.list("entity")
        if e.get("type") == "symbol" and e["source_ref"] == "src/auth/login.py"
    )
    assert impact.symbols_at(repository, ["src/auth/login.py"]) == ["src/auth/login.py::login"]
    requirement = repository.knowledge.apply(
        [
            {
                "name": "FR-1",
                "graph": "requirement",
                "type": "requirement",
                "source_ref": "specs/r.md",
                "authority": "contract",
                "confidence": 1,
                "observation": "DECLARED",
            }
        ],
        repository.store.knowledge_version,
        "approved",
    )["entities"][0]
    changed = next(
        e
        for e in repository.store.list("entity")
        if e.get("type") == "file" and e["source_ref"] == "src/auth/login.py"
    )
    repository.knowledge.link(requirement["id"], changed["id"], "implemented_by")
    assert impact.reached(repository, ["src/auth/login.py"])["dependent_requirements"] == [
        requirement["id"]
    ]

    with repository.store.transaction():
        repository.store.put("entity", {**symbol, "stale": True}, expected=symbol["version"])
        current = repository.store.get(requirement["id"], "entity")
        repository.store.put("entity", {**current, "stale": True}, expected=current["version"])

    assert impact.symbols_at(repository, ["src/auth/login.py"]) == []
    assert impact.reached(repository, ["src/auth/login.py"])["dependent_requirements"] == []


# --- the resolver ----------------------------------------------------------------------


def test_a_human_claim_waiting_for_its_verdict_says_why(repository: Any) -> None:
    task_id, _, accepted = _critical(repository)
    resolution = resolver.resolve(
        repository,
        repository.store.get(task_id, "task"),
        accepted,
        evidence=resolver.task_evidence(repository, task_id),
    )
    assert (resolution["status"], resolution["reason"]) == (
        "HUMAN_REQUIRED",
        "no automated verifier can settle this claim",
    )


def test_verified_and_waived_are_counted_separately(repository: Any) -> None:
    task_id, session = claimed(
        repository,
        contract(
            acceptance=["a", "b", "c"],
            verification=[spec("unit", [0]), spec("acceptance", [1]), spec("integration", [2])],
        ),
    )
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    third = next(o for o in obligations_for(repository, task_id) if o["claim"] == "c")
    with repository.store.transaction():
        repository.store.put("obligation", {**third, "status": "WAIVED"}, expected=third["version"])

    report = resolver.debt(repository, repository.store.get(task_id, "task"))

    assert (report["verified"], report["waived"]) == (2, 1)


# --- the service ------------------------------------------------------------------------


def _actors(plane: Any, action: str) -> set[str]:
    return {e["actor"] for e in plane.store.timeline(limit=1000) if e["action"] == action}


def test_a_registered_capability_is_attributed_to_the_owner(repository: Any) -> None:
    service.register_verifier(
        repository,
        {
            "id": "golden",
            "capabilities": ["reference_comparison"],
            "evidence_class": "DETERMINISTIC",
            "cost": "low",
            "level": 1,
        },
    )
    assert _actors(repository, "verifier_capability.write") == {"local-owner"}


def test_escalation_goes_past_a_claim_already_at_the_deepest_level(repository: Any) -> None:
    task_id, _ = claimed(repository, contract(risk="HIGH"))
    sources(repository.root, {"src/billing/invoice.py": "total = 0\n"})
    service.reconcile(repository, task_id)
    money = next(
        o for o in obligations_for(repository, task_id) if "FIN-STABLE" in o["origin"]["policy_ids"]
    )
    strength = next(
        o
        for o in obligations_for(repository, task_id)
        if "TEST-STRENGTH" in o["origin"]["policy_ids"]
    )
    with repository.store.transaction():
        repository.store.put("obligation", {**money, "floor": 4}, expected=money["version"])
    outstanding = [
        {"obligation_id": money["id"], "status": "UNKNOWN"},
        {"obligation_id": strength["id"], "status": "UNKNOWN"},
    ]

    assert service.escalate(repository, task_id, outstanding) == [strength["id"]]

    escalated = repository.store.get(strength["id"], "obligation")
    assert set(escalated) == set(strength)
    assert escalated["floor"] == strength["floor"] + 1
    assert _actors(repository, "assurance.escalate") == {"local"}


def test_a_failed_claim_is_run_again_and_a_changed_verdict_is_a_conflict(
    repository: Any, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Something outside the measured inputs changed the answer; that is not a pass."""
    flag = tmp_path_factory.mktemp("outside") / "flag"
    reads_flag = [
        sys.executable,
        "-c",
        f"import pathlib,sys;sys.exit(0 if pathlib.Path({str(flag)!r}).exists() else 1)",
    ]
    task_id, session = claimed(repository, contract(verification=[spec("unit", [0], reads_flag)]))
    service.compile_plan(repository, task_id, phase="INITIAL")
    first = service.verify(repository, task_id, session)
    assert first["decision"]["decision"] == "REPAIR"

    flag.write_text("present", encoding="utf-8")
    second = service.verify(repository, task_id, session)

    assert len(second["executions"]) == 1
    assert second["debt"]["required_counts"] == {"CONFLICTED": 1}
    assert second["decision"]["decision"] == "BLOCK"


def test_a_stale_human_verdict_is_not_handed_to_the_process_runner(repository: Any) -> None:
    task_id, session, accepted = _critical(repository)
    service.verify(repository, task_id, session)
    service.resolve_human(repository, accepted["id"], "accepted")
    (repository.root / "src" / "report.py").write_text("value = 1  # changed again\n")
    assert service.explain(repository, accepted["id"])["status"] == "STALE"

    outcome = service.verify(repository, task_id, session)

    run = [e["verifier"] for x in outcome["executions"] for e in x["evidence"]]
    assert not any(v.startswith("human:") for v in run)
    assert service.explain(repository, accepted["id"])["status"] == "STALE"


def test_a_superseded_task_is_left_out_of_the_project_status(repository: Any) -> None:
    replaced, session = claimed(repository)
    service.compile_plan(repository, replaced, phase="INITIAL")
    repository.release(replaced, session)
    repository.transition(replaced, "SUPERSEDED", "replaced by a better slice")
    assert service.status(repository)["tasks"] == []


def test_the_project_debt_report_covers_every_task_with_a_plan(repository: Any) -> None:
    task_id, _ = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    report = service.debt_report(repository)
    assert report["by_task"] == {task_id: 1}
    assert report["proof_debt"] == 1


def test_a_superseded_verdict_is_explained_as_superseded(repository: Any) -> None:
    task_id, session = claimed(
        repository,
        contract(
            verification=[
                spec("unit", [0]),
                spec("property", [], ["no-such-verifier-binary"]),
                spec("mutation", []),
            ],
            risk="HIGH",
        ),
    )
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    strength = next(
        o
        for o in obligations_for(repository, task_id)
        if "TEST-STRENGTH" in o["origin"]["policy_ids"]
    )
    currencies = {
        e["kind"]: e["currency"] for e in service.explain(repository, strength["id"])["evidence"]
    }
    assert currencies == {"mutation": "CURRENT", "property": "SUPERSEDED"}


def test_a_human_request_names_the_boundaries_the_change_is_accepted_against(
    repository: Any,
) -> None:
    task_id, _, accepted = _critical(repository, boundaries=["profitability domain"])
    request = service.explain(repository, accepted["id"])["human_request"]
    assert request["reference"] == ["profitability domain"]
    del task_id


def test_a_human_verdict_is_a_complete_evidence_record_the_rest_of_the_plane_can_read(
    repository: Any,
) -> None:
    task_id, _, accepted = _critical(repository)

    record = service.resolve_human(repository, accepted["id"], "accepted")["evidence"]

    assert record["id"].startswith("EVD-")
    assert set(record) == {
        "id",
        "version",
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
        "binding",
        "obligation_ids",
        "obligation_bindings",
        "knowledge_version",
        "artifact_hash",
        "artifact_ref",
        "started_at",
        "finished_at",
        "run_consistent",
        "stale",
    }
    # 2.0's own status and invalidation read every evidence record, this one included.
    assert repository.status()["evidence"]
    assert _actors(repository, "evidence.write") == {"local-owner"}
    assert _actors(repository, "decision.write") == {"local-owner"}
    del task_id


def test_a_waived_obligation_gains_only_its_waiver(repository: Any) -> None:
    task_id, _ = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    obligation = obligations_for(repository, task_id)[0]
    waived = service.waive(repository, obligation["id"], "accepted", "owner")["obligation"]
    assert set(waived) == set(obligation)
    assert (waived["status"], waived["waiver_id"] is not None) == ("WAIVED", True)


def test_integrity_findings_are_complete_records(repository: Any) -> None:
    task_id, _ = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    obligation = obligations_for(repository, task_id)[0]
    with repository.store.transaction():
        repository.store.put(
            "obligation", {**obligation, "status": "FAILED"}, expected=obligation["version"]
        )
    assert service.integrity(repository)["findings"] == [
        {
            "obligation_id": obligation["id"],
            "finding": "persisted status FAILED is not an owner state",
        }
    ]
    with repository.store.transaction():
        repository.store.db.execute("DELETE FROM records WHERE id=?", (obligation["id"],))
    assert service.integrity(repository)["findings"] == [
        {
            "task_id": task_id,
            "finding": "obligations recorded in an assurance plan are gone from the store",
            "obligations": [obligation["id"]],
        }
    ]


def _first_task(plane: Any) -> str:
    """A task record that sorts before every generated identifier."""
    with plane.store.transaction():
        plane.store.put("task", {"id": "TASK-0", "state": "PLANNED"})
    return "TASK-0"


def test_integrity_reads_past_a_task_without_a_plan(repository: Any) -> None:
    _first_task(repository)
    task_id, session = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    from assurance_support import checkpoint

    from agentic_discipline.control.verification import complete

    repository.checkpoint(task_id, session, checkpoint())
    complete(repository, task_id, session)
    (repository.root / "src" / "report.py").write_text("value = 2\n", encoding="utf-8")

    findings = service.integrity(repository)["findings"]

    assert [f["task_id"] for f in findings] == [task_id]


def test_integrity_reads_past_a_task_it_cannot_resolve(repository: Any) -> None:
    first = _first_task(repository)
    with repository.store.transaction():
        repository.store.put(
            "obligation",
            {
                "task_id": first,
                "status": "UNRESOLVED",
                "mandatory": True,
                "enforced": True,
            },
        )
    task_id, session = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    from assurance_support import checkpoint

    from agentic_discipline.control.verification import complete

    repository.checkpoint(task_id, session, checkpoint())
    complete(repository, task_id, session)
    (repository.root / "src" / "report.py").write_text("value = 2\n", encoding="utf-8")
    real = service.resolve_all

    def unreadable_first(plane: Any, task: dict[str, Any]) -> Any:
        if task["id"] == first:
            raise OSError("unreadable")
        return real(plane, task)

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(service, "resolve_all", unreadable_first)
        findings = service.integrity(repository)["findings"]

    assert [f["task_id"] for f in findings] == [task_id]


# --- migration ---------------------------------------------------------------------------


def test_the_migration_plan_counts_the_evidence_it_will_reclassify(repository: Any) -> None:
    task_id, session = claimed(repository)
    from agentic_discipline.control.verification import verify as run

    run(repository, task_id, session)
    _two_point_zero(repository)
    assert migration.plan(repository)["evidence_records"] == 1


def test_migration_classifies_by_a_kind_the_project_registered(repository: Any) -> None:
    service.register_verifier(
        repository,
        {
            "id": "golden",
            "capabilities": ["reference_comparison"],
            "evidence_class": "DETERMINISTIC",
            "cost": "low",
            "level": 1,
        },
    )
    task_id, session = claimed(repository, contract(verification=[spec("golden", [0])]))
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

    assert repository.store.get(record["id"], "evidence")["evidence_class"] == "DETERMINISTIC"


def test_migration_keeps_classifying_after_a_record_it_already_classified(
    repository: Any,
) -> None:
    task_id, session = claimed(repository)
    from agentic_discipline.control.verification import verify as run

    run(repository, task_id, session)
    (real,) = repository.store.list("evidence")
    with repository.store.transaction():
        repository.store.put(
            "evidence",
            {
                "id": "EVD-0",
                "task_id": task_id,
                "kind": "unit",
                "assurance_provenance": "LEGACY",
            },
        )
        repository.store.put(
            "evidence",
            {k: v for k, v in real.items() if k != "evidence_class"},
            expected=real["version"],
        )
    _two_point_zero(repository)

    result = migration.migrate(repository)

    assert result["reclassified_evidence"] == 1
    assert repository.store.get(real["id"], "evidence")["evidence_class"] == "DETERMINISTIC"


def test_migration_and_rollback_change_only_the_reversal_flag(repository: Any) -> None:
    task_id, _ = claimed(repository)
    _two_point_zero(repository)
    applied = migration.migrate(repository)
    before = obligations_for(repository, task_id)[0]

    migration.rollback(repository, applied["migration_id"], "reverting")
    reverted = repository.store.get(before["id"], "obligation")
    assert set(reverted) == set(before) | {"reverted"}

    migration.migrate(repository)
    revived = repository.store.get(before["id"], "obligation")
    assert set(revived) == set(before) | {"reverted"}
    assert revived["reverted"] is False
    rollback_writes = [
        e
        for e in repository.store.timeline(limit=1000)
        if e["action"] == "obligation.write" and e["payload"]["version"] == reverted["version"]
    ]
    assert {e["actor"] for e in rollback_writes} == {"local-owner"}


# --- permissions and symlinks, where the platform has them --------------------------------

posix = pytest.mark.skipif(os.name != "posix", reason="POSIX permissions and symlinks")


@posix
def test_a_human_verdict_artefact_is_private(repository: Any) -> None:
    _, _, accepted = _critical(repository)
    record = service.resolve_human(repository, accepted["id"], "accepted")["evidence"]
    artifact = repository.directory / "evidence" / f"{record['id']}.json"
    assert artifact.stat().st_mode & 0o777 == 0o600
    assert artifact.parent.stat().st_mode & 0o777 == 0o700


@posix
def test_a_human_verdict_refuses_a_symlinked_evidence_directory(
    repository: Any, tmp_path_factory: pytest.TempPathFactory
) -> None:
    _, _, accepted = _critical(repository)
    evidence = repository.directory / "evidence"
    if evidence.exists():
        import shutil

        shutil.rmtree(evidence)
    evidence.symlink_to(tmp_path_factory.mktemp("elsewhere"), target_is_directory=True)
    with pytest.raises(ControlError) as caught:
        service.resolve_human(repository, accepted["id"], "accepted")
    assert (caught.value.code, str(caught.value)) == (
        "INVALID_PATH",
        "Evidence directory must not be a symlink",
    )


# --- what a registered verifier may say about itself ------------------------------------


def test_a_registered_verifier_keeps_what_it_says_about_itself() -> None:
    entry = registry.normalized(
        {
            "id": "golden",
            "capabilities": ["reference_comparison"],
            "evidence_class": "DETERMINISTIC",
            "cost": "low",
            "level": 1,
            "ecosystems": ["python"],
            "required_inputs": ["reference/"],
            "produced_artifacts": ["artifacts/diff.json"],
        }
    )
    assert (entry["ecosystems"], entry["required_inputs"], entry["produced_artifacts"]) == (
        ["python"],
        ["reference/"],
        ["artifacts/diff.json"],
    )


@pytest.mark.parametrize("field", ["ecosystems", "required_inputs", "produced_artifacts"])
def test_each_declared_list_on_a_verifier_is_checked(field: str) -> None:
    with pytest.raises(ControlError) as caught:
        registry.descriptor_contract(
            {
                "id": "k",
                "capabilities": ["unit"],
                "evidence_class": "MEASURED",
                "cost": "low",
                "level": 1,
                field: [""],
            }
        )
    assert str(caught.value) == f"Invalid list: {field}"


def test_an_unreachable_claim_lists_every_capability_nobody_supplies() -> None:
    known = registry.Registry()
    route = planner.plan_for(
        {
            "id": "PO-1",
            "acceptable_proof_capabilities": ["migration_safety", "data_preservation"],
            "criticality": "LOW",
        },
        planner.pool({"verification": [spec("unit", [0])]}, known),
        known,
    )
    assert route["route"] == (
        "no declared verifier supplies an acceptable capability at depth 1 or deeper: "
        "data_preservation, migration_safety"
    )


def test_a_human_verdict_alone_going_stale_does_not_start_a_process(repository: Any) -> None:
    """Only a person can settle it again, so nothing is handed to the process runner."""
    task_id, session, accepted = _critical(repository)
    service.verify(repository, task_id, session)
    human = service.resolve_human(repository, accepted["id"], "accepted")["evidence"]
    (repository.directory / "evidence" / f"{human['id']}.json").unlink()
    report = resolver.debt(repository, repository.store.get(task_id, "task"))
    assert [(i["obligation_id"], i["status"]) for i in report["outstanding"]] == [
        (accepted["id"], "STALE")
    ]

    outcome = service.verify(repository, task_id, session)

    assert outcome["executions"] == []
    assert outcome["debt"]["required_counts"]["STALE"] == 1


# --- the last survivors of the full campaign ----------------------------------------------


def test_the_status_vocabulary_is_exactly_the_declared_one() -> None:
    assert model.STATUSES == {
        "UNRESOLVED",
        "VERIFYING",
        "VERIFIED",
        "FAILED",
        "UNKNOWN",
        "BLOCKED",
        "CONFLICTED",
        "STALE",
        "WAIVED",
        "HUMAN_REQUIRED",
    }


def test_a_compilation_says_which_phase_produced_it(repository: Any) -> None:
    from agentic_discipline.control.assurance import compiler

    task_id, _ = claimed(repository)
    task = repository.store.get(task_id, "task")
    known = registry.Registry()
    assert compiler.compile_obligations(repository, task, known, phase="INITIAL")["phase"] == (
        "INITIAL"
    )
    assert compiler.compile_obligations(repository, task, known, phase="RECONCILED")["phase"] == (
        "RECONCILED"
    )


def _link_requirement(plane: Any, path: str, authority: str) -> dict[str, Any]:
    plane.reconcile()
    file_entity = next(
        e for e in plane.store.list("entity") if e.get("type") == "file" and e["source_ref"] == path
    )
    requirement = plane.knowledge.apply(
        [
            {
                "name": f"FR {authority}",
                "graph": "requirement",
                "type": "requirement",
                "source_ref": "specs/r.md",
                "authority": authority,
                "confidence": 1,
                "observation": "DECLARED",
            }
        ],
        plane.store.knowledge_version,
        "approved",
    )["entities"][0]
    plane.knowledge.link(requirement["id"], file_entity["id"], "implemented_by")
    return requirement


def test_a_surface_reached_only_through_a_dependency_is_an_enforced_impact_claim(
    repository: Any,
) -> None:
    sources(repository.root, {"src/auth/session.py": "def check():\n    return True\n"})
    repository.reconcile()
    reached_file = next(
        e
        for e in repository.store.list("entity")
        if e.get("type") == "file" and e["source_ref"] == "src/auth/session.py"
    )
    changed_file = next(
        e
        for e in repository.store.list("entity")
        if e.get("type") == "file" and e["source_ref"] == "src/report.py"
    )
    repository.knowledge.link(reached_file["id"], changed_file["id"], "depends_on")
    task_id, _ = claimed(repository)

    (repository.root / "src" / "report.py").write_text("value = 2\n", encoding="utf-8")
    service.reconcile(repository, task_id)

    authorization = next(
        o for o in obligations_for(repository, task_id) if "SEC-AUTHZ" in o["origin"]["policy_ids"]
    )
    assert (
        authorization["derivation"],
        authorization["phase"],
        authorization["enforced"],
        authorization["affected_paths"],
        authorization["origin"]["generated_reason"],
    ) == (
        "IMPACT",
        "RECONCILED",
        True,
        ["src/auth/session.py"],
        "observed auth surface in src/auth/session.py; reached through recorded dependencies of"
        " the changed files",
    )


def test_a_requirement_a_human_approved_makes_its_impact_claim_mandatory(
    repository: Any,
) -> None:
    requirement = _link_requirement(repository, "src/other.py", "human")
    task_id, _ = claimed(repository)
    (repository.root / "src" / "other.py").write_text("unrelated = False\n", encoding="utf-8")
    service.reconcile(repository, task_id)
    reached = next(o for o in obligations_for(repository, task_id) if o["derivation"] == "IMPACT")
    assert reached["origin"]["requirement_ids"] == [requirement["id"]]
    assert reached["mandatory"] is True


def test_one_verify_call_runs_at_most_two_rounds(repository: Any) -> None:
    """The third, deeper route is selected and left for the next call, not run in this one."""
    service.register_verifier(
        repository,
        {
            "id": "deep-check",
            "capabilities": ["falsification"],
            "evidence_class": "DETERMINISTIC",
            "cost": "high",
            "level": 4,
        },
    )
    unrunnable = ["no-such-verifier-binary"]
    task_id, session = claimed(
        repository,
        contract(
            verification=[
                spec("unit", [0]),
                spec("property", [], unrunnable),
                spec("mutation", [], unrunnable),
                spec("deep-check", []),
            ],
            risk="HIGH",
        ),
    )
    service.compile_plan(repository, task_id, phase="INITIAL")

    outcome = service.verify(repository, task_id, session)

    assert len(outcome["executions"]) == 2
    assert outcome["decision"]["decision"] == "EXPAND_VERIFICATION"
    strength = next(
        o
        for o in obligations_for(repository, task_id)
        if "TEST-STRENGTH" in o["origin"]["policy_ids"]
    )
    assert strength["plan"]["route"].startswith("deep-check supplies falsification")
    assert service.verify(repository, task_id, session)["decision"]["decision"] == "COMPLETE"
