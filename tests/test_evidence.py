import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from agentic_discipline.common import AgenticError
from agentic_discipline.evidence import append_evidence, sha256_file, verify_ledger


def test_evidence_ledger_is_sequential(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_text('{"ok": true}', encoding="utf-8")
    ledger = tmp_path / "ledger.jsonl"

    first = append_evidence(ledger, artifact, tool="pytest", command="pytest", exit_code=0)
    second = append_evidence(ledger, artifact, tool="ruff", command="ruff check .", exit_code=0)

    assert first["sequence"] == 1
    assert second["sequence"] == 2
    assert first["artifact_sha256"] == sha256_file(artifact)
    assert second["previous_record_sha256"] == first["record_sha256"]
    assert verify_ledger(ledger, check_artifacts=True)["status"] == "PASS"


def test_evidence_ledger_detects_tampering(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_text('{"ok": true}', encoding="utf-8")
    ledger = tmp_path / "ledger.jsonl"
    append_evidence(ledger, artifact, tool="pytest", command="pytest", exit_code=0)
    record = json.loads(ledger.read_text(encoding="utf-8"))
    record["command"] = "echo fabricated"
    ledger.write_text(json.dumps(record) + "\n", encoding="utf-8")
    result = verify_ledger(ledger)
    assert result["status"] == "FAIL"
    assert any("record hash" in error for error in result["errors"])
    with pytest.raises(AgenticError, match="refusing to append"):
        append_evidence(ledger, artifact, tool="pytest", command="pytest", exit_code=0)


def test_empty_invalid_and_missing_artifact_ledgers_fail(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    assert verify_ledger(ledger)["status"] == "FAIL"
    ledger.write_text("not-json\n", encoding="utf-8")
    with pytest.raises(AgenticError, match="invalid evidence JSON"):
        verify_ledger(ledger)
    artifact = tmp_path / "missing.json"
    with pytest.raises(AgenticError, match="artifact not found"):
        append_evidence(tmp_path / "other.jsonl", artifact, tool="x", command="x", exit_code=1)


def test_concurrent_evidence_appends_are_serialized(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_text("{}", encoding="utf-8")
    ledger = tmp_path / "ledger.jsonl"

    def append(index: int) -> None:
        append_evidence(
            ledger,
            artifact,
            tool="worker",
            command=f"worker {index}",
            exit_code=0,
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(append, range(8)))
    result = verify_ledger(ledger, check_artifacts=True)
    assert result["status"] == "PASS"
    assert result["records"] == 8


def test_ledger_verifier_reports_sequence_chain_and_artifact_failures(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_text("{}", encoding="utf-8")
    ledger = tmp_path / "ledger.jsonl"
    record = append_evidence(ledger, artifact, tool="test", command="test", exit_code=0)

    record["sequence"] = 9
    record["previous_record_sha256"] = "wrong"
    record["artifact_sha256"] = "wrong"
    ledger.write_text(json.dumps(record) + "\n", encoding="utf-8")
    result = verify_ledger(ledger, check_artifacts=True)
    assert any("invalid sequence" in error for error in result["errors"])
    assert any("previous hash" in error for error in result["errors"])
    assert any("artifact hash" in error for error in result["errors"])

    record = {"sequence": 1}
    ledger.write_text(json.dumps(record) + "\n", encoding="utf-8")
    assert any("missing fields" in error for error in verify_ledger(ledger)["errors"])
