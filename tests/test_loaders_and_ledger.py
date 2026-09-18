"""What `init` passes on, what the ledger check reports, and how loaders explain failure.

Mutation testing found these outputs unchecked: an `init` option could stop reaching
`initialize_project`, the ledger verdict could rename its head hash or change the
message for an empty ledger, and the configuration loaders could lose the name of the
document or the separator between errors in their messages. Each case pins the exact
value.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline import cli
from agentic_discipline.common import AgenticError
from agentic_discipline.control.discovery import scan
from agentic_discipline.control.plane import Plane, adopt
from agentic_discipline.evidence import append_evidence, verify_ledger
from agentic_discipline.evolution import lifecycle_path, load_lifecycle
from agentic_discipline.validation import (
    ValidationError,
    load_quality_config,
    validate_quality_config,
    validate_schema,
)

# --- init -----------------------------------------------------------------------------------


def test_init_passes_every_option_to_initialize_project(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[Any, dict[str, Any]]] = []

    def initialize(target: Path, **options: Any) -> dict[str, Any]:
        calls.append((target, options))
        return {"status": "PASS"}

    monkeypatch.setattr(cli, "initialize_project", initialize)
    monkeypatch.setattr(cli, "_json", lambda data: None)
    args = argparse.Namespace(
        target=str(tmp_path),
        profile=["python"],
        profile_file=["extra.json"],
        force=True,
        max_depth=2,
        adapter=["claude"],
        dry_run=True,
        json=True,
    )

    assert cli.command_init(args) == 0
    assert cli.command_init(argparse.Namespace(**{**vars(args), "adapter": []})) == 0

    assert calls == [
        (
            tmp_path,
            {
                "profile_ids": ["python"],
                "profile_files": [Path("extra.json")],
                "force": True,
                "max_depth": 2,
                "adapters": ["claude"],
                "dry_run": True,
            },
        ),
        (
            tmp_path,
            {
                "profile_ids": ["python"],
                "profile_files": [Path("extra.json")],
                "force": True,
                "max_depth": 2,
                "adapters": None,
                "dry_run": True,
            },
        ),
    ]


# --- verify_ledger --------------------------------------------------------------------------


def _ledger(tmp_path: Path) -> tuple[Path, Path, dict[str, Any]]:
    artifact = tmp_path / "result.json"
    artifact.write_text("{}", encoding="utf-8")
    ledger = tmp_path / "ledger.jsonl"
    record = append_evidence(ledger, artifact, tool="pytest", command="pytest", exit_code=0)
    return ledger, artifact, record


def test_the_ledger_check_ignores_artifacts_unless_asked(tmp_path: Path) -> None:
    ledger, artifact, record = _ledger(tmp_path)
    artifact.unlink()

    assert verify_ledger(ledger) == {
        "status": "PASS",
        "records": 1,
        "head_sha256": record["record_sha256"],
        "errors": [],
    }
    assert verify_ledger(ledger, check_artifacts=True)["status"] == "FAIL"


def test_an_empty_ledger_fails_with_its_reason(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text("", encoding="utf-8")

    assert verify_ledger(ledger) == {
        "status": "FAIL",
        "records": 0,
        "head_sha256": None,
        "errors": ["ledger contains no evidence records"],
    }


def test_missing_fields_are_listed_in_one_message(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(json.dumps({"sequence": 1}) + "\n", encoding="utf-8")

    (error,) = verify_ledger(ledger)["errors"]

    assert error.startswith("record 1: missing fields artifact, artifact_sha256, command, ")


# --- configuration loaders ------------------------------------------------------------------


def test_a_broken_evolution_registry_is_named_in_the_error(tmp_path: Path) -> None:
    path = lifecycle_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("{", encoding="utf-8")

    with pytest.raises(ValidationError, match=r"^evolution registry is invalid JSON at line 1"):
        load_lifecycle(tmp_path)


def test_every_evolution_registry_error_is_reported(tmp_path: Path) -> None:
    registry: dict[str, Any] = {"artifacts": "none", "extra": True}
    path = lifecycle_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(registry), encoding="utf-8")
    errors = validate_schema(registry, "evolution.schema.json")
    assert len(errors) > 1

    with pytest.raises(AgenticError) as caught:
        load_lifecycle(tmp_path)

    assert str(caught.value) == "invalid evolution registry: " + "; ".join(errors)


def test_a_broken_quality_configuration_is_named_in_the_error(tmp_path: Path) -> None:
    path = tmp_path / "agentic.config.json"
    path.write_text("{", encoding="utf-8")

    with pytest.raises(ValidationError, match=r"^quality configuration is invalid JSON at line 1"):
        load_quality_config(path)


def test_every_quality_configuration_error_is_reported(tmp_path: Path) -> None:
    config: dict[str, Any] = {"schema_version": "9", "gates": "none"}
    path = tmp_path / "agentic.config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    errors = validate_quality_config(config)
    assert len(errors) > 1

    with pytest.raises(ValidationError) as caught:
        load_quality_config(path)

    assert str(caught.value) == "invalid quality configuration: " + "; ".join(errors)


# --- adopt ----------------------------------------------------------------------------------


def test_adoption_records_the_measured_coverage(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("value = 1\n", encoding="utf-8")
    expected = scan(tmp_path)["coverage"]

    adopt(tmp_path)

    with Plane(tmp_path) as plane:
        assert plane.store.list("project")[0]["coverage"] == expected
