"""Verifier registration, entry by entry.

`register_verifier` copies a verifier package into the project and records the
registry entry every later run, protection check and trust decision reads. Existing
tests registered verifiers as setup, so the entry path, the trust derived from
sensitivity, the metadata hash or the cleanup after a duplicate could change
unnoticed. Each case compares the exact registry entry and files.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline.common import AgenticError
from agentic_discipline.verifier.registry import load_registry, register_verifier, registry_path

PROVEN = {"method": "negative_control", "status": "PROVEN", "evidence": "proof.json"}


def _contract(identifier: str = "VER-REG", **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "schema_version": "1",
        "id": identifier,
        "name": "registration",
        "requirement_ids": ["REQ-REG"],
        "claim": "registration records the verifier",
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
    (path / "proof.json").write_text('{"status": "FAIL"}\n', encoding="utf-8")
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("from_file", [False, True])
def test_registration_copies_the_package_and_records_a_draft_entry(
    tmp_path: Path, from_file: bool
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source = _package(tmp_path / "source", _contract())

    entry = register_verifier(source / "verifier.json" if from_file else source, project)

    destination = project / ".agentic" / "verification" / "generated" / "VER-REG"
    assert entry == {
        "id": "VER-REG",
        "path": ".agentic/verification/generated/VER-REG",
        "trust": "DRAFT",
        "persistence": "durable",
        "last_validation": None,
        "metadata_sha256": _sha256(destination / "verifier.json"),
    }
    assert sorted(p.name for p in destination.iterdir()) == [
        "proof.json",
        "run.py",
        "verifier.json",
    ]
    written = registry_path(project).read_text(encoding="utf-8")
    assert json.loads(written) == {"schema_version": "1", "verifiers": [entry]}
    assert written.endswith("}\n") and "\n  " in written


def test_proven_sensitivity_registers_a_validated_verifier(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source = _package(tmp_path / "source", _contract(sensitivity=PROVEN))

    before = datetime.now(timezone.utc)
    entry = register_verifier(source, project)
    after = datetime.now(timezone.utc)

    assert entry["trust"] == "VALIDATED"
    validated = datetime.fromisoformat(entry["last_validation"])
    assert validated.tzinfo is not None
    assert before <= validated <= after


def test_later_registrations_are_appended_in_order(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    first = register_verifier(_package(tmp_path / "one", _contract("VER-ONE")), project)
    second = register_verifier(_package(tmp_path / "two", _contract("VER-TWO")), project)
    assert load_registry(project)["verifiers"] == [first, second]


def test_a_verifier_whose_directory_exists_is_refused_without_changes(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source = _package(tmp_path / "source", _contract())
    register_verifier(source, project)
    registry = registry_path(project).read_text(encoding="utf-8")

    with pytest.raises(AgenticError) as caught:
        register_verifier(source, project)

    assert str(caught.value) == "verifier already registered: VER-REG"
    assert registry_path(project).read_text(encoding="utf-8") == registry


def test_a_verifier_already_in_the_registry_is_refused_and_its_copy_removed(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source = _package(tmp_path / "source", _contract())
    register_verifier(source, project)
    destination = project / ".agentic" / "verification" / "generated" / "VER-REG"
    for child in destination.iterdir():
        child.unlink()
    destination.rmdir()
    registry = registry_path(project).read_text(encoding="utf-8")

    with pytest.raises(AgenticError) as caught:
        register_verifier(source, project)

    assert str(caught.value) == "verifier already registered: VER-REG"
    assert not destination.exists()
    assert registry_path(project).read_text(encoding="utf-8") == registry


def test_invalid_packages_are_refused_before_anything_is_copied(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source = _package(tmp_path / "source", _contract(timeout_seconds=0))
    with pytest.raises(AgenticError):
        register_verifier(source, project)
    assert not (project / ".agentic").exists()


def test_entry_paths_are_relative_to_the_resolved_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "project").mkdir()
    source = _package(tmp_path / "source", _contract())
    monkeypatch.chdir(tmp_path)
    entry = register_verifier(Path("source"), Path("project"))
    assert entry["path"] == ".agentic/verification/generated/VER-REG"
    assert (tmp_path / "project" / entry["path"] / "run.py").is_file()
    assert source.is_dir()


def test_registry_is_written_as_indented_json_creating_its_directories(tmp_path: Path) -> None:
    from agentic_discipline.verifier.registry import _write_registry

    registry = {"schema_version": "1", "verifiers": [{"id": "VER-1"}]}
    _write_registry(tmp_path, registry)
    assert registry_path(tmp_path).read_text(encoding="utf-8") == (
        json.dumps(registry, indent=2) + "\n"
    )


def test_a_missing_registry_is_empty(tmp_path: Path) -> None:
    assert load_registry(tmp_path) == {"schema_version": "1", "verifiers": []}


def test_unreadable_or_invalid_registries_are_named(tmp_path: Path) -> None:
    from agentic_discipline.validation import ValidationError, validate_schema

    path = registry_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ValidationError) as unreadable:
        load_registry(tmp_path)
    assert str(unreadable.value).startswith("verifier registry is invalid JSON at line 1")

    invalid = {"schema_version": "2", "verifiers": "none", "extra": True}
    path.write_text(json.dumps(invalid), encoding="utf-8")
    errors = validate_schema(invalid, "verifier-registry.schema.json")
    assert len(errors) > 1
    with pytest.raises(AgenticError) as caught:
        load_registry(tmp_path)
    assert str(caught.value) == "invalid verifier registry: " + "; ".join(errors)
