"""Defaults and orderings the assurance tests always supplied, so a mutant could keep them.

Each case omits the value the production code fills in, or arranges the store so a
`continue` and a `break` disagree. Equivalent substitutions, where None and False
are the same test, stay in the reviewed exception list.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from assurance_support import claimed, contract, sources

from agentic_discipline.control.api import call
from agentic_discipline.control.assurance import impact, migration, resolver, service
from agentic_discipline.control.contracts import digest
from agentic_discipline.control.plane import Plane, adopt


@pytest.fixture
def plane(tmp_path: Path) -> Any:
    sources(tmp_path, {"src/report.py": "value = 1\n"})
    adopt(tmp_path)
    with Plane(tmp_path) as opened:
        yield opened


def test_a_task_without_a_recorded_file_baseline_is_measured_against_its_workspace(
    plane: Any,
) -> None:
    task_id, _ = claimed(plane)
    task = plane.store.get(task_id, "task")
    without_files = {key: value for key, value in task.items() if key != "initial_files"}

    assert impact.changed_paths(plane, without_files) == []


def test_a_task_without_a_recorded_link_baseline_treats_every_link_as_new(plane: Any) -> None:
    task_id, _ = claimed(plane)
    task = plane.store.get(task_id, "task")
    without_links = {key: value for key, value in task.items() if key != "initial_links"}

    assert impact.changed_paths(plane, without_links) == impact.changed_paths(
        plane, {**without_links, "initial_links": {}}
    )


def test_falsification_names_the_files_the_diff_touched_not_the_declared_scope(plane: Any) -> None:
    task_id, _ = claimed(plane, contract(risk="HIGH"))
    (plane.root / "src" / "report.py").write_text("value = 2\n", encoding="utf-8")
    task = plane.store.get(task_id, "task")
    changed = impact.changed_paths(plane, task)
    service.compile_plan(plane, task_id, phase="RECONCILED")

    strength = next(
        obligation
        for obligation in service.obligations_for(plane, task_id)
        if "TEST-STRENGTH" in obligation["origin"]["policy_ids"]
    )

    assert changed and changed != list(task["scope"])
    assert strength["affected_paths"] == changed


def test_rollback_still_reverts_a_migrated_obligation_that_sorts_after_a_stranger(
    plane: Any,
) -> None:
    task_id, _ = claimed(plane)
    applied = migration.migrate(plane)
    with plane.store.transaction():
        plane.store.put(
            "obligation",
            {"id": "A-not-migrated", "task_id": task_id, "status": "UNRESOLVED"},
        )

    result = migration.rollback(plane, applied["migration_id"], "the upgrade has to wait")

    migrated = [
        obligation
        for obligation in plane.store.list("obligation")
        if obligation["id"] != "A-not-migrated"
    ]
    assert result["obligations_retired"] == len(migrated) > 0
    assert all(obligation["reverted"] for obligation in migrated)
    assert plane.store.get("A-not-migrated", "obligation").get("reverted") is not True


def test_a_waiver_with_no_reason_is_an_integrity_finding(plane: Any) -> None:
    task_id, _ = claimed(plane)
    service.compile_plan(plane, task_id, phase="INITIAL")
    obligation = service.obligations_for(plane, task_id)[0]
    waiver = service.waive(plane, obligation["id"], "accepted", "owner")["waiver"]
    stored = {key: value for key, value in waiver.items() if key not in {"reason", "version"}}
    with plane.store.transaction():
        plane.store.put("waiver", stored, expected=waiver["version"])

    assert service.integrity(plane)["findings"] == [
        {
            "obligation_id": obligation["id"],
            "finding": "waived without a recorded waiver",
        }
    ]


def test_an_omitted_human_acceptance_counts_as_accepted(plane: Any) -> None:
    task_id, _ = claimed(plane)
    service.compile_plan(plane, task_id, phase="INITIAL")
    obligation = service.obligations_for(plane, task_id)[0]
    with plane.store.transaction():
        plane.store.put(
            "obligation",
            {
                **obligation,
                "affected_paths": ["src/report.py"],
                "required_verifiers": [f"human:{obligation['id']}"],
                "plan": {**obligation["plan"], "human_required": True},
            },
            expected=obligation["version"],
        )

    evidence = call(
        plane,
        "assurance_resolve_human",
        {"obligation_id": obligation["id"], "decision": "the report reads correctly"},
        local=True,
    )["data"]["evidence"]

    assert (evidence["result"], evidence["judgment"]) == ("PASS", "ACCEPTED")


def test_migration_runs_when_dry_run_is_left_out(plane: Any) -> None:
    assert call(plane, "assurance_migrate", {}, local=True)["data"]["migrated"] is True


def test_resolving_an_obligation_with_no_plan_names_the_missing_route(plane: Any) -> None:
    task_id, _ = claimed(plane)
    service.compile_plan(plane, task_id, phase="INITIAL")
    obligation = service.obligations_for(plane, task_id)[0]
    bare = {key: value for key, value in obligation.items() if key != "plan"}
    bare["required_verifiers"] = []
    task = plane.store.get(task_id, "task")

    resolution = resolver.resolve(plane, task, bare, evidence=[])

    assert (resolution["status"], resolution["reason"]) == (
        "UNKNOWN",
        "no verifier is selected for this claim",
    )
    assert resolution["binding_digest"] == digest(resolver.obligation_binding(plane, task, bare))


def test_legacy_evidence_uses_the_task_binding_when_none_was_supplied(plane: Any) -> None:
    task_id, session = claimed(plane)
    service.compile_plan(plane, task_id, phase="INITIAL")
    service.verify(plane, task_id, session)
    task = plane.store.get(task_id, "task")
    obligation = next(
        item
        for item in service.obligations_for(plane, task_id)
        if item["derivation"] == "CONTRACT"
    )
    legacy = [
        {**record, "obligation_bindings": {}, "obligation_ids": [obligation["id"]]}
        for record in plane.store.list("evidence")
        if record["task_id"] == task_id
    ]

    resolution = resolver.resolve(plane, task, obligation, evidence=legacy, task_binding=None)

    assert resolution["status"] == "VERIFIED"
