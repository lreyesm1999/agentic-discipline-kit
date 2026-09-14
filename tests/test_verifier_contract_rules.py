"""Verifier contract rules, asserted by their specific outcome.

The broader edge tests call ``validate_verifier`` with partial dictionaries. Those
always fail JSON Schema validation, so a bare ``assert errors`` still passes when
the rule under test is deleted. Every test here starts from a schema-valid
contract and checks the exact message or behaviour the rule produces.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline.bootstrap import initialize_project
from agentic_discipline.common import AgenticError
from agentic_discipline.validation import ValidationError
from agentic_discipline.verifier.executor import _safe_working_directory, execute_verifier
from agentic_discipline.verifier.protection import protect_verifier
from agentic_discipline.verifier.registry import (
    load_registry,
    load_verifier,
    register_verifier,
    registry_path,
)
from agentic_discipline.verifier.schema import load_and_validate_verifier, validate_verifier
from agentic_discipline.verifier.sensitivity import sensitivity_status

ESCAPE = "working_directory: must stay inside the project root"
MISSING_EVIDENCE = "sensitivity.evidence: required when status is PROVEN"
UNPROVEN_PROTECTED = "protected verifiers must have PROVEN sensitivity"
PROVEN = {"method": "negative_control", "status": "PROVEN", "evidence": "proof.json"}


def _contract(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "schema_version": "1",
        "id": "VER-RULES",
        "name": "rules",
        "requirement_ids": ["REQ-RULES"],
        "claim": "contract rules are enforced",
        "type": "custom",
        "origin": "handwritten",
        "risk": "LOW",
        "command": [sys.executable, "run.py"],
        "timeout_seconds": 10,
        "working_directory": ".",
        "expected_exit_code": 0,
        "artifacts": [],
        "sensitivity": {"method": "negative_control", "status": "UNPROVEN"},
        "persistence": "durable",
        "protected": False,
    }
    data.update(overrides)
    return data


def _package(path: Path, contract: dict[str, Any]) -> Path:
    path.mkdir(parents=True)
    (path / "verifier.json").write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    (path / "run.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    return path


def _registered_proven(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    initialize_project(project)
    source = _package(tmp_path / "source", _contract(sensitivity=PROVEN))
    (source / "proof.json").write_text('{"status":"FAIL"}\n', encoding="utf-8")
    register_verifier(source, project)
    return project


def test_schema_valid_contract_has_no_errors() -> None:
    assert validate_verifier(_contract()) == []


@pytest.mark.parametrize("escape", ["../escape", "nested/../../escape"])
def test_working_directory_with_parent_segments_is_rejected(escape: str) -> None:
    assert ESCAPE in validate_verifier(_contract(working_directory=escape))


def test_absolute_working_directory_is_rejected(tmp_path: Path) -> None:
    assert ESCAPE in validate_verifier(_contract(working_directory=str(tmp_path)))


def test_project_relative_working_directory_is_accepted() -> None:
    assert validate_verifier(_contract(working_directory="tools/verify")) == []


def test_proven_sensitivity_requires_evidence() -> None:
    missing = {"method": "negative_control", "status": "PROVEN"}
    assert MISSING_EVIDENCE in validate_verifier(_contract(sensitivity=missing))
    assert MISSING_EVIDENCE in validate_verifier(_contract(sensitivity={**missing, "evidence": ""}))
    assert validate_verifier(_contract(sensitivity=PROVEN)) == []


def test_protected_contract_requires_proven_sensitivity() -> None:
    assert UNPROVEN_PROTECTED in validate_verifier(_contract(protected=True))
    assert validate_verifier(_contract(protected=True, sensitivity=PROVEN)) == []
    assert UNPROVEN_PROTECTED not in validate_verifier(_contract(protected=False))


def test_loading_an_invalid_contract_fails_with_its_errors(tmp_path: Path) -> None:
    path = tmp_path / "verifier.json"
    path.write_text(json.dumps(_contract(protected=True)), encoding="utf-8")
    with pytest.raises(AgenticError, match="invalid verifier contract: " + UNPROVEN_PROTECTED):
        load_and_validate_verifier(path)
    with pytest.raises((AgenticError, ValidationError), match="verifier contract not found"):
        load_and_validate_verifier(tmp_path / "absent.json")


def test_sensitivity_without_proof_is_draft(tmp_path: Path) -> None:
    assert sensitivity_status({}, tmp_path, tmp_path) == "DRAFT"


def test_sensitivity_evidence_is_found_in_the_project_root(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    package = tmp_path / "package"
    package.mkdir()
    (project / "proof.json").write_text("{}\n", encoding="utf-8")
    assert sensitivity_status({"sensitivity": PROVEN}, project, package) == "VALIDATED"


def test_sensitivity_evidence_cannot_escape_the_project_root(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    package = tmp_path / "deep" / "package"
    package.mkdir(parents=True)
    (tmp_path / "secret.json").write_text("{}\n", encoding="utf-8")
    metadata = {"sensitivity": {**PROVEN, "evidence": "../secret.json"}}
    with pytest.raises(AgenticError, match="sensitivity evidence not found"):
        sensitivity_status(metadata, project, package)


def test_intact_protected_verifier_loads(tmp_path: Path) -> None:
    project = _registered_proven(tmp_path)
    protect_verifier(project, "VER-RULES")
    metadata, directory = load_verifier(project, "VER-RULES")
    assert metadata["id"] == "VER-RULES"
    assert (directory / "verifier.json").is_file()


def test_protected_verifier_with_deleted_contract_is_reported_changed(tmp_path: Path) -> None:
    project = _registered_proven(tmp_path)
    protect_verifier(project, "VER-RULES")
    _, directory = load_verifier(project, "VER-RULES")
    (directory / "verifier.json").unlink()
    with pytest.raises(AgenticError, match="protected verifier changed: VER-RULES"):
        load_verifier(project, "VER-RULES")


def test_metadata_hash_is_only_enforced_for_protected_entries(tmp_path: Path) -> None:
    project = _registered_proven(tmp_path)
    registry = load_registry(project)
    registry["verifiers"][0]["metadata_sha256"] = "0" * 64
    registry_path(project).write_text(json.dumps(registry), encoding="utf-8")
    metadata, _ = load_verifier(project, "VER-RULES")
    assert metadata["id"] == "VER-RULES"


def test_registry_that_violates_its_schema_or_json_is_rejected(tmp_path: Path) -> None:
    project = tmp_path / "project"
    initialize_project(project)
    registry_path(project).parent.mkdir(parents=True, exist_ok=True)
    registry_path(project).write_text('{"schema_version":"1","verifiers":{}}', encoding="utf-8")
    with pytest.raises(AgenticError, match="invalid verifier registry: verifiers"):
        load_registry(project)
    registry_path(project).write_text("{not json", encoding="utf-8")
    with pytest.raises((AgenticError, ValidationError), match="verifier registry is invalid JSON"):
        load_registry(project)


def test_verifier_runs_in_its_declared_project_directory(tmp_path: Path) -> None:
    project = tmp_path / "project"
    initialize_project(project)
    (project / "work").mkdir()
    record_cwd = (
        "import os, pathlib; "
        "pathlib.Path(os.environ['ADK_RESULT_PATH']).write_text(os.getcwd(), encoding='utf-8')"
    )
    contract = _contract(working_directory="work", command=[sys.executable, "-c", record_cwd])
    register_verifier(_package(tmp_path / "source", contract), project)

    result = execute_verifier(project, "VER-RULES")

    assert result["status"] == "PASS"
    raw = project / ".agentic" / "verification" / "artifacts" / "VER-RULES.raw.json"
    assert Path(raw.read_text(encoding="utf-8")).resolve() == (project / "work").resolve()


def test_working_directory_outside_the_project_is_refused(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / "inside").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    assert _safe_working_directory(project, "inside") == (project / "inside").resolve()
    with pytest.raises(AgenticError, match="project-relative directory"):
        _safe_working_directory(project, str(outside))
    with pytest.raises(AgenticError, match="project-relative directory"):
        _safe_working_directory(project, "missing")


def test_missing_environment_variable_blocks_and_present_one_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    name = "ADK_CONTRACT_RULES_TOKEN"
    monkeypatch.delenv(name, raising=False)
    project = tmp_path / "project"
    initialize_project(project)
    register_verifier(_package(tmp_path / "source", _contract(requires={"env": [name]})), project)

    blocked = execute_verifier(project, "VER-RULES")
    assert blocked["status"] == "BLOCKED"
    assert blocked["observations"]["missing_env"] == [name]

    monkeypatch.setenv(name, "present")
    assert execute_verifier(project, "VER-RULES")["status"] == "PASS"


def test_package_artifacts_outside_the_project_are_not_hashed(tmp_path: Path) -> None:
    project = tmp_path / "project"
    initialize_project(project)
    # The registered package lives four levels below the project root.
    (tmp_path / "outside.txt").write_text("secret\n", encoding="utf-8")
    contract = _contract(artifacts=["../../../../outside.txt", "local.txt"])
    source = _package(tmp_path / "source", contract)
    (source / "local.txt").write_text("inside\n", encoding="utf-8")
    register_verifier(source, project)

    result = execute_verifier(project, "VER-RULES")

    assert result["status"] == "PASS"
    assert [item["path"] for item in result["artifacts"]] == [
        ".agentic/verification/generated/VER-RULES/local.txt"
    ]
