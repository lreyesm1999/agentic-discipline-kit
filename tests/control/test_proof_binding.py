"""Proof binding, evidence freshness and live proof of completed work.

A completed task only counts while its proof is bound to the current files,
requirements, canonical constraints, dependencies, verifiers and policy. Existing
tests checked a few invalidations through full workflows, so a binding field, a
freshness condition or one reason proof stops being current could change unnoticed.
Each case pins the exact binding or verdict.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import pytest
from conftest import checkpoint, contract
from test_kernel import entity

from agentic_discipline.control.contracts import ControlError, digest
from agentic_discipline.control.discovery import fingerprint
from agentic_discipline.control.verification import (
    binding,
    complete,
    fresh,
    proof_current,
    verify,
)

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX symlinks")


def _force(project: Any, kind: str, identifier: str, **fields: Any) -> dict[str, Any]:
    with project.store.transaction():
        current = project.store.get(identifier, kind)
        return project.store.put(kind, {**current, **fields}, expected=current["version"])


def _requirement(project: Any, name: str = "Orders") -> dict[str, Any]:
    (created,) = project.knowledge.apply([entity(name)], project.store.knowledge_version, "seed")[
        "entities"
    ]
    return created


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


def _completed(project: Any, **changes: Any) -> dict[str, Any]:
    data = {**contract(), **changes}
    project.approve_command(data["verification"][0]["command"])
    task = project.create_task(data)["id"]
    project.ready(task)
    session = project.join("worker", ["code", "terminal"])["session"]
    project.claim(task, session)
    project.checkpoint(task, session, checkpoint())
    verify(project, task, session)
    complete(project, task, session)
    return project.store.get(task, "task")


# --- binding --------------------------------------------------------------------------------


def test_binding_records_every_input_the_proof_depends_on(project: Any) -> None:
    requirement = _requirement(project)
    canonical = _claim(project, requirement["id"], "human", 30)
    contract_claim = project.knowledge.claim(
        {
            "subject": requirement["id"],
            "predicate": "archive_days",
            "value": 365,
            "source_ref": "contract.md",
            "authority": "contract",
            "confidence": 1,
            "observation": "DECLARED",
        }
    )
    (project.root / "notes.md").write_text("outside the task scope", encoding="utf-8")
    _claim(project, requirement["id"], "documentation", 30)
    other = _requirement(project, "Invoices")
    _claim(project, other["id"], "contract", 1)
    dependency = _completed(project)
    task = {
        **contract(),
        "state": "CLAIMED",
        "requirements": [requirement["id"]],
        "dependencies": [dependency["id"]],
    }
    policy = project.policy()

    assert binding(project, task) == {
        "files": fingerprint(project.root, ["app.py", "test_app.py", "."]),
        "requirements": {requirement["id"]: 1},
        "canonical_constraints": {
            canonical["id"]: canonical["version"],
            contract_claim["id"]: contract_claim["version"],
        },
        "protected_files": fingerprint(project.root, policy["protected_paths"]),
        "dependencies": {dependency["id"]: dependency["proof"]},
        "verification": digest(task["verification"]),
        "acceptance": digest(task["acceptance"]),
        "policy": digest(policy),
    }


def test_declared_verifier_inputs_narrow_the_measured_files(project: Any) -> None:
    (unit,) = contract()["verification"]
    task = {
        **contract(),
        "state": "CLAIMED",
        "scope": ["app.py"],
        "verification": [{**unit, "inputs": ["test_app.py"]}],
    }
    (project.root / "unrelated.txt").write_text("x", encoding="utf-8")
    assert binding(project, task)["files"] == fingerprint(project.root, ["app.py", "test_app.py"])


def test_binding_refuses_unmeasured_inputs(project: Any) -> None:
    (unit,) = contract()["verification"]
    task = {**contract(), "state": "CLAIMED", "verification": [{**unit, "inputs": [".env"]}]}
    with pytest.raises(ControlError) as caught:
        binding(project, task)
    assert (caught.value.code, str(caught.value)) == (
        "UNTRACKED_INPUT",
        "Verifier input is excluded from measurement",
    )


# --- fresh ----------------------------------------------------------------------------------


def _evidence(project: Any, content: bytes = b'{"ok": true}') -> dict[str, Any]:
    artifact = project.directory / "evidence" / "EVID-test.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(content)
    return {
        "id": "EVID-test",
        "binding": {"files": {"a": "1"}},
        "artifact_hash": hashlib.sha256(content).hexdigest(),
    }


def test_evidence_is_fresh_only_with_the_same_binding_and_untouched_artifact(
    project: Any,
) -> None:
    evidence = _evidence(project)
    assert fresh(project, evidence, {"files": {"a": "1"}}) is True
    assert fresh(project, evidence, {"files": {"a": "2"}}) is False
    assert fresh(project, {**evidence, "artifact_hash": "0" * 64}, evidence["binding"]) is False
    (project.directory / "evidence" / "EVID-test.json").unlink()
    assert fresh(project, evidence, evidence["binding"]) is False
    assert fresh(project, {**evidence, "id": "EVID-other"}, evidence["binding"]) is False


@posix_only
def test_symlinked_evidence_is_never_fresh(project: Any, tmp_path: Path) -> None:
    evidence = _evidence(project)
    evidence_dir = project.directory / "evidence"
    real = tmp_path / "real-evidence"
    real.mkdir()
    target = real / "EVID-test.json"
    target.write_bytes((evidence_dir / "EVID-test.json").read_bytes())

    (evidence_dir / "EVID-test.json").unlink()
    (evidence_dir / "EVID-test.json").symlink_to(target)
    assert fresh(project, evidence, evidence["binding"]) is False

    (evidence_dir / "EVID-test.json").unlink()
    evidence_dir.rmdir()
    evidence_dir.symlink_to(real, target_is_directory=True)
    assert fresh(project, evidence, evidence["binding"]) is False


# --- proof_current --------------------------------------------------------------------------


def test_completed_work_with_current_proof_is_current(project: Any) -> None:
    task = _completed(project, requirements=[_requirement(project)["id"]])
    assert proof_current(project, task) is True
    assert proof_current(project, task, set()) is True
    _claim(project, task["requirements"][0], "documentation", 30)
    assert proof_current(project, project.store.get(task["id"], "task")) is True


def test_unfinished_or_already_visited_work_is_not_current(project: Any) -> None:
    task = _completed(project)
    assert proof_current(project, {**task, "state": "VERIFYING"}) is False
    assert proof_current(project, task, {task["id"]}) is False


def test_conflicting_or_newly_canonical_knowledge_invalidates_proof(project: Any) -> None:
    requirement = _requirement(project)
    task = _completed(project, requirements=[requirement["id"]])
    _claim(project, requirement["id"], "code", 30)
    _claim(project, requirement["id"], "code", 60)
    assert proof_current(project, task) is False

    other_requirement = _requirement(project, "Invoices")
    other = _completed(project, requirements=[other_requirement["id"]])
    _claim(project, other_requirement["id"], "human", 90)
    assert proof_current(project, other) is False


@pytest.mark.parametrize(
    "change",
    [{"stale": True}, {"result": "FAIL"}],
    ids=["stale", "failed"],
)
def test_stale_or_failed_evidence_invalidates_proof(project: Any, change: dict[str, Any]) -> None:
    task = _completed(project)
    (evidence_id,) = task["proof"]
    _force(project, "evidence", evidence_id, **change)
    assert proof_current(project, task) is False


def test_changed_files_or_tampered_artifacts_invalidate_proof(project: Any) -> None:
    task = _completed(project)
    (project.root / "app.py").write_text("value = 1\n# edited later\n", encoding="utf-8")
    assert proof_current(project, task) is False

    second = _completed(project, scope=["test_app.py"])
    (evidence_id,) = second["proof"]
    artifact = project.directory / "evidence" / f"{evidence_id}.json"
    artifact.write_bytes(artifact.read_bytes() + b" ")
    assert proof_current(project, second) is False


def test_proof_must_cover_every_verifier_and_exist(project: Any) -> None:
    task = _completed(project)
    assert proof_current(project, {**task, "proof": []}) is False
    assert proof_current(project, {**task, "proof": ["EVID-missing"]}) is False


@pytest.mark.parametrize(
    "change", [{"lifecycle": "RETIRED"}, {"stale": True}], ids=["retired", "stale"]
)
def test_inactive_requirements_invalidate_proof(project: Any, change: dict[str, Any]) -> None:
    requirement = _requirement(project)
    task = _completed(project, requirements=[requirement["id"]])
    _force(project, "entity", requirement["id"], **change)
    assert proof_current(project, task) is False


def _finish(project: Any, task_id: str) -> dict[str, Any]:
    project.ready(task_id)
    session = project.join("worker", ["code", "terminal"])["session"]
    project.claim(task_id, session)
    project.checkpoint(task_id, session, checkpoint())
    verify(project, task_id, session)
    complete(project, task_id, session)
    return project.store.get(task_id, "task")


def test_dependencies_must_themselves_be_current(project: Any) -> None:
    # Approve once: approving again changes the policy every binding records.
    project.approve_command(contract()["verification"][0]["command"])
    dependency_id = project.create_task({**contract(), "scope": ["test_app.py"]})["id"]
    task_id = project.create_task({**contract(), "dependencies": [dependency_id]})["id"]
    dependency = _finish(project, dependency_id)
    task = _finish(project, task_id)
    assert proof_current(project, task) is True
    _force(project, "task", dependency["id"], state="VERIFYING")
    assert proof_current(project, task) is False


# --- checks behind freshness ----------------------------------------------------------------


def _past_freshness(monkeypatch: pytest.MonkeyPatch) -> None:
    # A changed requirement or dependency already makes the evidence stale; these cases
    # test the checks that stand behind freshness.
    import agentic_discipline.control.verification as verification

    monkeypatch.setattr(verification, "fresh", lambda plane, evidence, current: True)


@pytest.mark.parametrize("fields", [{"lifecycle": "RETIRED"}, {"stale": True}])
def test_a_retired_or_stale_requirement_ends_proof_even_past_freshness(
    project: Any, monkeypatch: pytest.MonkeyPatch, fields: dict[str, Any]
) -> None:
    requirement = _requirement(project)
    task = _completed(project, requirements=[requirement["id"]])
    _past_freshness(monkeypatch)
    assert proof_current(project, task) is True

    _force(project, "entity", requirement["id"], **fields)

    assert proof_current(project, task) is False


def test_a_dependency_cycle_ends_proof_even_past_freshness(
    project: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _completed(project)
    second = _completed(project)
    _force(project, "task", first["id"], dependencies=[second["id"]])
    _force(project, "task", second["id"], dependencies=[first["id"]])
    _past_freshness(monkeypatch)

    assert proof_current(project, project.store.get(first["id"], "task")) is False
