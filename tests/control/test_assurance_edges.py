"""The edges of the assurance engine: no plan, unreadable records, dependency reach.

These paths decide what the engine says when something is missing or broken, which is
exactly where a wrong answer would be a confident one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from assurance_support import BUDGET, FAILS, checkpoint, claimed, contract, sources, spec

from agentic_discipline.control.assurance import migration, resolver, service
from agentic_discipline.control.assurance.decision import decide, mandatory_debt, repairable
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


# --- no plan at all -------------------------------------------------------------------


def test_without_a_compiled_plan_the_engine_says_so_instead_of_approving(
    repository: Any,
) -> None:
    task_id, _ = claimed(repository)
    task = repository.store.get(task_id, "task")

    assert mandatory_debt(repository, task) == []
    decision = decide(repository, task, {"outstanding": [], "proof_debt": 0, "required_counts": {}})
    assert decision["decision"] == "CONTINUE"
    assert decision["reasons"] == ["no assurance plan has been compiled for this task"]
    assert decision["completion_allowed"] is False


def test_a_task_with_no_obligations_is_absent_from_the_project_status(
    repository: Any,
) -> None:
    claimed(repository)
    assert service.status(repository)["tasks"] == []
    assert service.debt_report(repository)["proof_debt"] == 0


def test_a_severe_claim_no_verifier_reaches_escalates_rather_than_asking_for_a_run(
    repository: Any,
) -> None:
    task_id, _ = claimed(repository, contract(risk="HIGH"))
    service.reconcile(repository, task_id)
    task = repository.store.get(task_id, "task")
    report = resolver.debt(repository, task)

    decision = decide(repository, task, report)

    assert decision["decision"] == "ESCALATE"
    assert any("is UNKNOWN" in r for r in decision["reasons"])
    assert any("Declare a verifier that can supply" in a for a in decision["next_actions"])


def test_a_lesser_claim_no_verifier_reaches_also_escalates_once_the_rest_is_proven(
    repository: Any,
) -> None:
    """Nothing is left to run, so asking for another run would be the wrong answer."""
    task_id, session = claimed(repository, contract(scope=["src", "deploy"]))
    sources(repository.root, {"deploy/pipeline.yml": "steps: []\n"})
    service.reconcile(repository, task_id)
    service.verify(repository, task_id, session)
    task = repository.store.get(task_id, "task")
    report = resolver.debt(repository, task)

    decision = decide(repository, task, report)

    assert report["required_counts"] == {"UNKNOWN": 1, "VERIFIED": 1}
    assert decision["decision"] == "ESCALATE"
    assert any("cannot be resolved by any declared verifier" in r for r in decision["reasons"])


def test_a_spent_retry_budget_ends_the_authority_to_repair(repository: Any) -> None:
    task_id, session = claimed(
        repository,
        contract(verification=[spec("unit", [0], FAILS)], budget={**BUDGET, "max_retries": 0}),
    )
    service.compile_plan(repository, task_id, phase="INITIAL")
    obligation = obligations_for(repository, task_id)[0]
    outstanding = [{"obligation_id": obligation["id"], "status": "FAILED"}]

    assert repairable(repository, repository.store.get(task_id, "task"), outstanding) is True
    service.verify(repository, task_id, session)
    assert repairable(repository, repository.store.get(task_id, "task"), outstanding) is False


# --- unreadable or broken records -------------------------------------------------------


def test_an_unreadable_evidence_artefact_proves_nothing(repository: Any) -> None:
    task_id, session = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    record = repository.store.list("evidence")[0]
    artifact = repository.directory / "evidence" / f"{record['id']}.json"

    artifact.write_text("not json at all", encoding="utf-8")

    assert resolver.outcome_matches(repository, record) is False
    artifact.unlink()
    assert resolver.outcome_matches(repository, record) is False


def test_an_artefact_holding_a_different_exit_code_proves_nothing(repository: Any) -> None:
    task_id, session = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    record = repository.store.list("evidence")[0]
    artifact = repository.directory / "evidence" / f"{record['id']}.json"
    payload = json.loads(artifact.read_text(encoding="utf-8"))

    artifact.write_text(json.dumps({**payload, "exit_code": 7}), encoding="utf-8")

    assert resolver.outcome_matches(repository, record) is False
    artifact.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    assert resolver.outcome_matches(repository, record) is False


def test_resolving_a_task_with_no_obligations_returns_nothing_to_report(
    repository: Any,
) -> None:
    task_id, _ = claimed(repository)
    assert resolver.resolve_all(repository, repository.store.get(task_id, "task")) == []


def test_a_task_binding_that_cannot_be_read_does_not_become_a_pass(
    repository: Any,
) -> None:
    task_id, session = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    task = repository.store.get(task_id, "task")

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "agentic_discipline.control.verification.binding",
            lambda plane, task: (_ for _ in ()).throw(OSError("unreadable tree")),
        )
        resolutions = resolver.resolve_all(repository, task)

    # The per-obligation binding still holds, so the claim is still current and the
    # expensive task-wide binding is never read.
    assert [r["status"] for r in resolutions] == ["VERIFIED"]


def test_a_record_with_no_binding_of_its_own_falls_back_and_stays_conservative(
    repository: Any,
) -> None:
    """A 2.0 record has only the task-wide binding, so an unreadable tree leaves it stale."""
    task_id, session = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    record = repository.store.list("evidence")[0]
    with repository.store.transaction():
        repository.store.put(
            "evidence", {**record, "obligation_bindings": {}}, expected=record["version"]
        )
    task = repository.store.get(task_id, "task")

    assert [r["status"] for r in resolver.resolve_all(repository, task)] == ["VERIFIED"]

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "agentic_discipline.control.verification.binding",
            lambda plane, task: (_ for _ in ()).throw(OSError("unreadable tree")),
        )
        resolutions = resolver.resolve_all(repository, task)

    assert [r["status"] for r in resolutions] == ["STALE"]


def test_an_obligation_whose_paths_cannot_be_measured_is_reported_not_skipped(
    repository: Any,
) -> None:
    task_id, session = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    obligation = obligations_for(repository, task_id)[0]
    with repository.store.transaction():
        repository.store.put(
            "obligation",
            {**obligation, "affected_paths": [".git/config"]},
            expected=obligation["version"],
        )

    with pytest.raises(ControlError) as caught:
        service.status(repository, task_id)

    assert caught.value.code == "UNTRACKED_INPUT"


# --- integrity edges -------------------------------------------------------------------


def _two_point_zero(plane: Any) -> None:
    """Put the project back on the 2.0 schema, as an upgraded installation would find it."""
    with plane.store.transaction():
        plane.store.db.execute("UPDATE meta SET value='1' WHERE key='schema_version'")
    plane.store.schema_version = 1


def test_the_integrity_check_says_nothing_applies_before_the_migration(
    repository: Any,
) -> None:
    claimed(repository)
    _two_point_zero(repository)

    report = service.integrity(repository)

    assert report == {"status": "NOT_APPLICABLE", "findings": [], "obligations": 0}


def test_evidence_without_the_run_that_made_it_is_reported(repository: Any) -> None:
    task_id, session = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    record = repository.store.list("evidence")[0]

    with repository.store.transaction():
        repository.store.put("evidence", {**record, "run_id": ""}, expected=record["version"])

    report = service.integrity(repository)
    assert report["status"] == "FAIL"
    assert any(
        f["finding"] == "evidence does not reference the execution that created it"
        for f in report["findings"]
    )


def test_an_unreadable_task_does_not_hide_the_rest_of_the_integrity_report(
    repository: Any,
) -> None:
    task_id, session = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    obligation = obligations_for(repository, task_id)[0]
    with repository.store.transaction():
        repository.store.put(
            "obligation", {**obligation, "status": "FAILED"}, expected=obligation["version"]
        )

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            resolver,
            "resolve_all",
            lambda plane, task: (_ for _ in ()).throw(OSError("unreadable")),
        )
        monkeypatch.setattr(service, "resolve_all", resolver.resolve_all)
        report = service.integrity(repository)

    assert report["status"] == "FAIL"
    assert report["findings"][0]["finding"] == "persisted status FAILED is not an owner state"


# --- debt views ------------------------------------------------------------------------


def test_proof_debt_can_be_read_by_requirement_and_by_criticality(repository: Any) -> None:
    requirement = repository.knowledge.apply(
        [
            {
                "name": "FR-032 broker profitability",
                "graph": "requirement",
                "type": "requirement",
                "source_ref": "specs/profit.md",
                "authority": "contract",
                "confidence": 1,
                "observation": "DECLARED",
            }
        ],
        repository.store.knowledge_version,
        "approved requirement",
    )["entities"][0]
    task_id, _ = claimed(repository, contract(requirements=[requirement["id"]], risk="HIGH"))
    service.reconcile(repository, task_id)

    report = service.debt_report(repository, task_id)

    assert report["proof_debt"] == 2
    assert report["by_task"] == {task_id: 2}
    assert report["by_requirement"] == {requirement["id"]: 2}
    assert report["by_criticality"] == {"HIGH": 2}
    # The same areas discovery classifies, so debt reads by part of the repository too.
    assert report["by_area"] == {"source": 2}
    assert report["stale_evidence"] == []


def test_the_debt_report_names_the_evidence_that_stopped_speaking_for_a_claim(
    repository: Any,
) -> None:
    """After a change invalidates something, the question left is which evidence went stale."""
    task_id, session = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    recorded = repository.store.list("evidence")[0]["id"]
    assert service.debt_report(repository, task_id)["stale_evidence"] == []

    (repository.root / "src" / "report.py").write_text("value = 2\n", encoding="utf-8")

    report = service.debt_report(repository, task_id)
    assert report["stale_evidence"] == [recorded]
    assert report["by_area"] == {"source": 1}


# --- dependency reach ------------------------------------------------------------------


def test_a_requirement_that_depends_on_a_changed_file_gains_its_own_obligation(
    repository: Any,
) -> None:
    """Expansion through recorded links: the change reaches beyond the file it edited."""
    repository.reconcile()
    file_entity = next(
        e
        for e in repository.store.list("entity")
        if e.get("type") == "file" and e["source_ref"] == "src/other.py"
    )
    requirement = repository.knowledge.apply(
        [
            {
                "name": "FR-010 unrelated reporting",
                "graph": "requirement",
                "type": "requirement",
                "source_ref": "specs/report.md",
                "authority": "contract",
                "confidence": 1,
                "observation": "DECLARED",
            }
        ],
        repository.store.knowledge_version,
        "approved requirement",
    )["entities"][0]
    repository.knowledge.link(requirement["id"], file_entity["id"], "implemented_by")
    task_id, _ = claimed(repository)

    (repository.root / "src" / "other.py").write_text("unrelated = False\n", encoding="utf-8")
    plan = service.reconcile(repository, task_id)

    assert plan["impact"]["dependent_requirements"] == [requirement["id"]]
    reached = next(o for o in obligations_for(repository, task_id) if o["derivation"] == "IMPACT")
    assert (
        reached["claim"] == "Requirement FR-010 unrelated reporting still holds after this change."
    )
    assert reached["mandatory"] is True
    assert reached["origin"]["requirement_ids"] == [requirement["id"]]
    assert "depends on a file this change modified" in reached["origin"]["generated_reason"]


def test_a_retired_dependent_does_not_expand_the_plan(repository: Any) -> None:
    repository.reconcile()
    file_entity = next(
        e
        for e in repository.store.list("entity")
        if e.get("type") == "file" and e["source_ref"] == "src/other.py"
    )
    requirement = repository.knowledge.apply(
        [
            {
                "name": "FR-011 withdrawn",
                "graph": "requirement",
                "type": "requirement",
                "source_ref": "specs/report.md",
                "authority": "documentation",
                "confidence": 1,
                "observation": "DECLARED",
            }
        ],
        repository.store.knowledge_version,
        "approved requirement",
    )["entities"][0]
    repository.knowledge.link(requirement["id"], file_entity["id"], "implemented_by")
    repository.knowledge.lifecycle(requirement["id"], "RETIRED", "feature withdrawn")
    task_id, _ = claimed(repository)

    (repository.root / "src" / "other.py").write_text("unrelated = False\n", encoding="utf-8")
    plan = service.reconcile(repository, task_id)

    assert plan["impact"]["dependent_requirements"] == []
    assert [o["derivation"] for o in obligations_for(repository, task_id)] == ["CONTRACT"]


# --- escalation edges ------------------------------------------------------------------


def test_escalation_stops_at_the_deepest_level(repository: Any) -> None:
    task_id, _ = claimed(repository, contract(risk="HIGH"))
    service.reconcile(repository, task_id)
    strength = next(
        o
        for o in obligations_for(repository, task_id)
        if "TEST-STRENGTH" in o["origin"]["policy_ids"]
    )
    with repository.store.transaction():
        repository.store.put("obligation", {**strength, "floor": 4}, expected=strength["version"])
    outstanding = [{"obligation_id": strength["id"], "status": "UNKNOWN"}]

    assert service.escalate(repository, task_id, outstanding) == []


def test_a_contract_obligation_is_never_escalated_away_from_its_own_verifiers(
    repository: Any,
) -> None:
    task_id, _ = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    obligation = obligations_for(repository, task_id)[0]
    outstanding = [{"obligation_id": obligation["id"], "status": "UNKNOWN"}]

    assert service.escalate(repository, task_id, outstanding) == []
    # The depth it was recorded at, and no deeper.
    assert repository.store.get(obligation["id"], "obligation")["floor"] == obligation["level"]


def test_assurance_verify_stops_once_nothing_is_left_to_run(repository: Any) -> None:
    task_id, session = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")

    outcome = service.verify(repository, task_id, session, rounds=5)

    # One round was enough, so the loop did not spend the retry budget on more.
    assert len(outcome["executions"]) == 1
    assert repository.store.get(task_id, "task")["attempts"] == 1


def test_assurance_verify_needs_the_engine_to_be_enabled(repository: Any) -> None:
    task_id, session = claimed(repository)
    with repository.store.transaction():
        repository.store.db.execute("UPDATE meta SET value='1' WHERE key='schema_version'")
    repository.store.schema_version = 1

    with pytest.raises(ControlError) as caught:
        service.verify(repository, task_id, session)

    assert caught.value.code == "ASSURANCE_DISABLED"


def test_registering_a_verifier_needs_the_engine_to_be_enabled(repository: Any) -> None:
    with repository.store.transaction():
        repository.store.db.execute("UPDATE meta SET value='1' WHERE key='schema_version'")
    repository.store.schema_version = 1

    with pytest.raises(ControlError) as caught:
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

    assert caught.value.code == "ASSURANCE_DISABLED"


# --- migration edges -------------------------------------------------------------------


def test_migrating_an_already_migrated_project_reports_it_without_changing_anything(
    repository: Any,
) -> None:
    claimed(repository)
    report = migration.plan(repository)
    assert report["already_migrated"] is True
    assert report["from_schema"] == "2"


@pytest.mark.parametrize(
    ("reason", "authorization"),
    [("", "owner"), ("   ", "owner"), ("accepted", ""), ("accepted", "  ")],
)
def test_a_waiver_needs_both_a_reason_and_the_authority_behind_it(
    repository: Any, reason: str, authorization: str
) -> None:
    task_id, _ = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    obligation = obligations_for(repository, task_id)[0]

    with pytest.raises(ControlError) as caught:
        service.waive(repository, obligation["id"], reason, authorization)

    assert (caught.value.code, str(caught.value)) == (
        "DECISION_REQUIRED",
        "A waiver needs a reason and the authority that granted it",
    )


def test_a_waived_claim_is_explained_with_the_waiver_behind_it(repository: Any) -> None:
    task_id, session = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    obligation = obligations_for(repository, task_id)[0]
    service.waive(repository, obligation["id"], "accepted for the spike", "owner")

    explained = service.explain(repository, obligation["id"])

    assert explained["status"] == "WAIVED"
    assert explained["waiver"]["reason"] == "accepted for the spike"
    assert explained["waiver"]["status_when_waived"] == "UNRESOLVED"
    assert explained["evidence"] == []
    # A waived claim no longer blocks completion, and the waiver stays on the record.
    repository.checkpoint(task_id, session, checkpoint())
    from agentic_discipline.control.verification import verify as run

    run(repository, task_id, session)
    assert complete(repository, task_id, session)["state"] == "COMPLETED"


def test_a_second_migration_leaves_evidence_it_has_already_classified_alone(
    repository: Any,
) -> None:
    task_id, session = claimed(repository)
    from agentic_discipline.control.verification import verify as run

    run(repository, task_id, session)
    _two_point_zero(repository)
    assert migration.migrate(repository)["reclassified_evidence"] == 1
    _two_point_zero(repository)

    second = migration.migrate(repository)

    assert second["reclassified_evidence"] == 0
    assert len(repository.store.list("evidence")) == 1


def test_a_rollback_leaves_alone_the_obligations_it_did_not_create(
    repository: Any,
) -> None:
    first_task, first_session = claimed(repository)
    _two_point_zero(repository)
    applied = migration.migrate(repository)
    repository.release(first_task, first_session)
    later_task, _ = claimed(repository, contract(objective="A later slice"))
    service.compile_plan(repository, later_task, phase="INITIAL")
    assert obligations_for(repository, later_task)

    migration.rollback(repository, applied["migration_id"], "reverting the upgrade")

    assert obligations_for(repository, first_task) == []
    # This one was compiled after the migration, so the rollback record does not name it.
    assert len(obligations_for(repository, later_task)) == 1


def test_assurance_verify_with_nothing_runnable_escalates_without_a_run(
    repository: Any,
) -> None:
    task_id, session = claimed(repository, contract(risk="HIGH"))
    service.compile_plan(repository, task_id, phase="INITIAL")
    service.verify(repository, task_id, session)
    attempts = repository.store.get(task_id, "task")["attempts"]

    again = service.verify(repository, task_id, session)

    assert again["executions"] == []
    assert repository.store.get(task_id, "task")["attempts"] == attempts
    assert again["decision"]["decision"] == "ESCALATE"


def test_assurance_verify_stops_at_its_round_limit_instead_of_looping(
    repository: Any,
) -> None:
    """One round is granted, so the escalated route waits for the next call to be run."""
    task_id, session = claimed(
        repository,
        contract(
            acceptance=["The report renders"],
            verification=[
                spec("unit", [0]),
                spec("property", [], ["no-such-verifier-binary"]),
                spec("mutation", []),
            ],
            risk="HIGH",
        ),
    )
    service.compile_plan(repository, task_id, phase="INITIAL")

    outcome = service.verify(repository, task_id, session, rounds=1)

    assert len(outcome["executions"]) == 1
    assert outcome["escalated"]
    assert outcome["decision"]["decision"] == "EXPAND_VERIFICATION"
    # The deeper route is selected and waiting, not silently dropped.
    strength = next(
        o
        for o in obligations_for(repository, task_id)
        if "TEST-STRENGTH" in o["origin"]["policy_ids"]
    )
    assert strength["floor"] == 3
    assert strength["plan"]["route"].startswith("mutation supplies")
    assert service.verify(repository, task_id, session)["decision"]["decision"] == "COMPLETE"


def test_a_legitimate_waiver_passes_the_integrity_check(repository: Any) -> None:
    task_id, _ = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    obligation = obligations_for(repository, task_id)[0]
    service.waive(repository, obligation["id"], "accepted for the spike", "owner")

    report = service.integrity(repository)

    assert report["status"] == "PASS"
    assert report["waivers"] == 1


# --- the focused-run path ----------------------------------------------------------------


def test_only_the_verifier_whose_claim_went_stale_is_run_again(repository: Any) -> None:
    """The point of binding a claim narrowly: a rerun costs one verifier, not all of them."""
    task_id, session = claimed(
        repository,
        contract(
            acceptance=["The report renders"],
            verification=[spec("unit", [0]), spec("security", [])],
            risk="STANDARD",
        ),
    )
    sources(repository.root, {"src/auth/login.py": "def login():\n    return True\n"})
    service.reconcile(repository, task_id)
    service.verify(repository, task_id, session)
    assert service.status(repository, task_id)["tasks"][0]["counts"] == {"VERIFIED": 2}
    before = len(repository.store.list("evidence"))

    # A file the authorization claim does not depend on, so only the acceptance claim moves.
    (repository.root / "src" / "other.py").write_text("unrelated = False\n", encoding="utf-8")
    outcome = service.verify(repository, task_id, session)

    assert len(repository.store.list("evidence")) - before == 1
    assert [e["kind"] for e in outcome["executions"][0]["evidence"]] == ["unit"]
    assert outcome["decision"]["decision"] == "COMPLETE"

    # Every claim is resolved, and the conservative 2.0 gate still asks for the whole scope
    # to be proven again before the task may complete. LIMITATIONS.md records this.
    repository.checkpoint(task_id, session, checkpoint())
    with pytest.raises(ControlError) as caught:
        complete(repository, task_id, session)
    assert caught.value.code == "STALE_OR_FAILED_EVIDENCE"


def test_a_claim_whose_paths_cannot_be_measured_does_not_stop_the_run(
    repository: Any,
) -> None:
    """A binding the engine cannot read binds the run to no claim, rather than failing it."""
    task_id, session = claimed(repository)
    service.compile_plan(repository, task_id, phase="INITIAL")
    obligation = obligations_for(repository, task_id)[0]
    with repository.store.transaction():
        repository.store.put(
            "obligation",
            {**obligation, "affected_paths": [".git/config"]},
            expected=obligation["version"],
        )
    from agentic_discipline.control.verification import assurance_stamps, verify

    task = repository.store.get(task_id, "task")
    assert assurance_stamps(repository, task) == {}

    result = verify(repository, task_id, session)

    assert result["status"] == "PASS"
    (record,) = repository.store.list("evidence")
    assert record["obligation_ids"] == []
