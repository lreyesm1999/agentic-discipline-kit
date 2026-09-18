"""Listing commands: `adapters list`, `verifier list`, `verifier register`, `evidence`.

These print a JSON document other tools read by key. Existing tests ran them and
checked the exit code, so a renamed key, a dropped field or a wrong source table
would be invisible: the command still succeeds and still prints something. Each
case compares the printed document whole.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline import cli
from agentic_discipline.adapters import ADAPTERS, ALIASES, EMITTERS, LABELS
from agentic_discipline.bootstrap import initialize_project

VERIFIER_ID = "VER-LISTING"


@pytest.fixture
def printed(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    output: list[Any] = []
    monkeypatch.setattr(cli, "_json", output.append)
    return output


def _args(**values: Any) -> argparse.Namespace:
    return argparse.Namespace(**values)


def _verifier_source(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    contract = {
        "schema_version": "1",
        "id": VERIFIER_ID,
        "name": "listing",
        "requirement_ids": ["REQ-LISTING"],
        "claim": "listings are exact",
        "type": "custom",
        "origin": "handwritten",
        "risk": "LOW",
        "command": [sys.executable, "run.py"],
        "timeout_seconds": 30,
        "working_directory": ".",
        "expected_exit_code": 0,
        "artifacts": [],
        "sensitivity": {"method": "negative_control", "status": "UNPROVEN"},
        "persistence": "durable",
        "protected": False,
    }
    (directory / "verifier.json").write_text(json.dumps(contract, indent=2), encoding="utf-8")
    (directory / "run.py").write_text("pass\n", encoding="utf-8")
    return directory


def test_adapters_list_reports_every_dialect_with_its_label_and_output(
    printed: list[Any], tmp_path: Path
) -> None:
    project = tmp_path / "project"
    project.mkdir()

    assert cli.command_adapters_list(_args(project_root=str(project))) == 0

    assert printed == [
        {
            "status": "PASS",
            "adapters": [
                {"id": name, "label": LABELS[name], "output": ADAPTERS[name]}
                for name in sorted(EMITTERS)
            ],
            "aliases": ALIASES,
            "detected": ["generic"],
        }
    ]
    # Every dialect the kit can emit is offered, with somewhere to write it.
    listed = {entry["id"] for entry in printed[0]["adapters"]}
    assert listed == set(EMITTERS)


def test_adapters_list_detects_the_tools_a_project_already_uses(
    printed: list[Any], tmp_path: Path
) -> None:
    project = tmp_path / "project"
    (project / ".cursor").mkdir(parents=True)
    (project / ".claude").mkdir()

    cli.command_adapters_list(_args(project_root=str(project)))

    assert printed[0]["detected"] == ["generic", "claude", "cursor"]


def test_verifier_register_then_list_reports_the_registered_entry(
    printed: list[Any], tmp_path: Path
) -> None:
    project = tmp_path / "project"
    initialize_project(project)
    source = _verifier_source(tmp_path / "source")

    assert cli.command_verifier_register(_args(path=str(source), project_root=str(project))) == 0
    registered = printed[0]
    assert registered["status"] == "PASS"
    assert registered["registered"]["id"] == VERIFIER_ID

    assert cli.command_verifier_list(_args(project_root=str(project))) == 0
    assert printed[1] == {"status": "PASS", "verifiers": [registered["registered"]]}


def test_verifier_inspect_reports_the_contract_and_where_it_lives(
    printed: list[Any], tmp_path: Path
) -> None:
    project = tmp_path / "project"
    initialize_project(project)
    cli.command_verifier_register(
        _args(path=str(_verifier_source(tmp_path / "source")), project_root=str(project))
    )

    assert (
        cli.command_verifier_inspect(_args(project_root=str(project), verifier_id=VERIFIER_ID)) == 0
    )

    inspected = printed[1]
    assert inspected["status"] == "PASS"
    assert inspected["verifier"]["id"] == VERIFIER_ID
    assert Path(inspected["directory"]).name == VERIFIER_ID


def test_evidence_records_the_run_and_reports_the_tool_exit_code(
    printed: list[Any], tmp_path: Path
) -> None:
    artifact = tmp_path / "result.json"
    artifact.write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
    ledger = tmp_path / "evidence-ledger.jsonl"

    code = cli.command_evidence(
        _args(
            ledger=str(ledger),
            artifact=str(artifact),
            tool="pytest",
            executed_command="pytest -q",
            exit_code=0,
        )
    )

    assert code == 0
    record = printed[0]
    assert record["tool"] == "pytest"
    assert record["command"] == "pytest -q"
    assert record["exit_code"] == 0
    assert ledger.read_text(encoding="utf-8").strip()


def test_evidence_of_a_failed_run_is_recorded_and_reported_as_failure(
    printed: list[Any], tmp_path: Path
) -> None:
    artifact = tmp_path / "result.json"
    artifact.write_text(json.dumps({"status": "FAIL"}), encoding="utf-8")

    code = cli.command_evidence(
        _args(
            ledger=str(tmp_path / "evidence-ledger.jsonl"),
            artifact=str(artifact),
            tool="pytest",
            executed_command="pytest -q",
            exit_code=1,
        )
    )

    assert code == 1
    assert printed[0]["exit_code"] == 1
