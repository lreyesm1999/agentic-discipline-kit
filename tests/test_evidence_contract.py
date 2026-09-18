"""Evidence ledger format and diagnostics, pinned by known answers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from agentic_discipline.common import AgenticError
from agentic_discipline.evidence import _record_hash, append_evidence, sha256_file, verify_ledger


def _artifact(tmp_path: Path) -> Path:
    artifact = tmp_path / "artifact.json"
    artifact.write_text("{}", encoding="utf-8")
    return artifact


def test_sha256_file_hashes_content_larger_than_one_read_chunk(tmp_path: Path) -> None:
    payload = bytes(range(256)) * 600  # 153,600 bytes: several 65,536-byte reads
    artifact = tmp_path / "large.bin"
    artifact.write_bytes(payload)
    assert sha256_file(artifact) == hashlib.sha256(payload).hexdigest()


def test_record_hash_is_sha256_of_compact_sorted_json() -> None:
    # Existing ledgers are verified against this exact serialization; changing it
    # would invalidate every recorded chain.
    record = {"tool": "pytest", "sequence": 1, "nested": {"b": 2, "a": 1}}
    canonical = '{"nested":{"a":1,"b":2},"sequence":1,"tool":"pytest"}'
    assert _record_hash(record) == hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_appended_record_is_utc_sorted_and_created_in_a_new_directory(tmp_path: Path) -> None:
    ledger = tmp_path / "nested" / "evidence" / "ledger.jsonl"
    record = append_evidence(ledger, _artifact(tmp_path), tool="t", command="t", exit_code=0)

    assert record["timestamp_utc"].endswith("+00:00")
    line = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
    assert list(line) == sorted(line)
    assert verify_ledger(ledger)["status"] == "PASS"


def test_every_record_with_missing_fields_is_reported(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(
        json.dumps({"sequence": 1}) + "\n" + json.dumps({"sequence": 2}) + "\n", encoding="utf-8"
    )
    errors = verify_ledger(ledger)["errors"]
    assert [error.split(":")[0] for error in errors] == ["record 1", "record 2"]


def test_invalid_json_reports_its_line_number(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text("{}\nnot json\n", encoding="utf-8")
    with pytest.raises(AgenticError, match="invalid evidence JSON at line 2"):
        verify_ledger(ledger)
