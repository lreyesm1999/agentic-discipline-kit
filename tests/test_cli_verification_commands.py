"""`evidence-verify` and `verifier protect`, run as a user types them.

Both commands were only exercised through the library functions they call, so the
argument names the parser hands them, the exit code and the printed document were
untested: a renamed option or a command reporting PASS on a broken ledger would
pass the suite. Each case parses a real command line and checks all three.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline import cli
from agentic_discipline.bootstrap import initialize_project
from agentic_discipline.common import AgenticError
from agentic_discipline.evidence import append_evidence
from agentic_discipline.verifier.registry import load_registry, register_verifier

VERIFIER_ID = "VER-CLI-PROTECT"


@pytest.fixture
def printed(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    output: list[Any] = []
    monkeypatch.setattr(cli, "_json", output.append)
    return output


def _run(*argv: str) -> int:
    args = cli.build_parser().parse_args(list(argv))
    return int(args.func(args))


def _ledger(tmp_path: Path) -> tuple[Path, Path]:
    artifact = tmp_path / "result.json"
    artifact.write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
    ledger = tmp_path / "evidence-ledger.jsonl"
    append_evidence(ledger, artifact, tool="pytest", command="pytest -q", exit_code=0)
    return ledger, artifact


def _verifier_source(directory: Path, status: str) -> Path:
    directory.mkdir()
    contract = {
        "schema_version": "1",
        "id": VERIFIER_ID,
        "name": "cli protect",
        "requirement_ids": ["REQ-CLI"],
        "claim": "the protect command protects a validated verifier",
        "type": "custom",
        "origin": "generated",
        "risk": "STANDARD",
        "command": ["python", "run.py"],
        "timeout_seconds": 10,
        "working_directory": ".",
        "expected_exit_code": 0,
        "sensitivity": {
            "method": "known_bad_fixture",
            "evidence": "sensitivity.json",
            "status": status,
        },
        "persistence": "durable",
        "protected": False,
    }
    (directory / "verifier.json").write_text(json.dumps(contract, indent=2), encoding="utf-8")
    (directory / "run.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    (directory / "sensitivity.json").write_text('{"status":"FAIL"}\n', encoding="utf-8")
    return directory


def test_evidence_verify_passes_an_intact_ledger(printed: list[Any], tmp_path: Path) -> None:
    ledger, _artifact = _ledger(tmp_path)

    assert _run("evidence-verify", "--ledger", str(ledger), "--check-artifacts") == 0

    assert printed[0]["status"] == "PASS"
    assert printed[0]["records"] == 1
    assert printed[0]["errors"] == []


def test_evidence_verify_checks_artifacts_only_when_asked(
    printed: list[Any], tmp_path: Path
) -> None:
    ledger, artifact = _ledger(tmp_path)
    artifact.write_text(json.dumps({"status": "FAIL"}), encoding="utf-8")

    assert _run("evidence-verify", "--ledger", str(ledger)) == 0
    assert _run("evidence-verify", "--ledger", str(ledger), "--check-artifacts") == 1

    assert printed[0]["status"] == "PASS"
    assert printed[1]["status"] == "FAIL"
    assert printed[1]["errors"] == ["record 1: artifact hash does not match"]


def test_verifier_protect_marks_a_validated_verifier_protected(
    printed: list[Any], tmp_path: Path
) -> None:
    project = tmp_path / "project"
    initialize_project(project)
    register_verifier(_verifier_source(tmp_path / "source", "PROVEN"), project)

    assert _run("verifier", "protect", VERIFIER_ID, "--project-root", str(project)) == 0

    assert printed[0]["status"] == "PASS"
    assert printed[0]["protected"]["id"] == VERIFIER_ID
    assert printed[0]["protected"]["trust"] == "PROTECTED"
    assert printed[0]["protected"]["metadata_sha256"]
    # What was printed is what the registry now holds.
    assert load_registry(project)["verifiers"] == [printed[0]["protected"]]


def test_verifier_protect_refuses_an_unproven_verifier(tmp_path: Path) -> None:
    project = tmp_path / "project"
    initialize_project(project)
    register_verifier(_verifier_source(tmp_path / "source", "UNPROVEN"), project)
    before = load_registry(project)

    with pytest.raises(AgenticError, match="only sensitivity-validated"):
        _run("verifier", "protect", VERIFIER_ID, "--project-root", str(project))

    assert load_registry(project) == before
    assert before["verifiers"][0]["trust"] == "DRAFT"
