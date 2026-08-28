from __future__ import annotations

import hashlib
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .common import AgenticError


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record_hash(record: dict[str, Any]) -> str:
    encoded = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@contextmanager
def _ledger_lock(ledger: Path, timeout_seconds: float = 10.0) -> Any:
    lock = ledger.with_suffix(ledger.suffix + ".lock")
    deadline = time.monotonic() + timeout_seconds
    descriptor: int | None = None
    while descriptor is None:
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise AgenticError(f"timed out waiting for evidence ledger lock: {lock}") from None
            time.sleep(0.05)
    try:
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        os.close(descriptor)
        descriptor = None
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        lock.unlink(missing_ok=True)


def _read_records(ledger: Path) -> list[dict[str, Any]]:
    if not ledger.exists():
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(ledger.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AgenticError(f"invalid evidence JSON at line {line_number}: {exc.msg}") from exc
        if not isinstance(record, dict):
            raise AgenticError(f"invalid evidence record at line {line_number}")
        records.append(record)
    return records


def append_evidence(
    ledger: Path,
    artifact: Path,
    *,
    tool: str,
    command: str,
    exit_code: int,
) -> dict[str, Any]:
    if not artifact.is_file():
        raise AgenticError(f"evidence artifact not found: {artifact}")
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with _ledger_lock(ledger):
        records = _read_records(ledger)
        if records:
            verification = verify_ledger(ledger)
            if verification["status"] != "PASS":
                raise AgenticError(
                    "refusing to append to an invalid evidence ledger: "
                    + "; ".join(verification["errors"])
                )
        previous_hash = records[-1].get("record_sha256") if records else None
        record: dict[str, Any] = {
            "sequence": len(records) + 1,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "tool": tool,
            "command": command,
            "exit_code": exit_code,
            "status": "PASS" if exit_code == 0 else "FAIL",
            "artifact": str(artifact.resolve()),
            "artifact_sha256": sha256_file(artifact),
            "previous_record_sha256": previous_hash,
        }
        record["record_sha256"] = _record_hash(record)
        with ledger.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    return record


def verify_ledger(ledger: Path, check_artifacts: bool = False) -> dict[str, Any]:
    records = _read_records(ledger)
    errors: list[str] = []
    previous_hash: str | None = None
    required = {
        "sequence",
        "timestamp_utc",
        "tool",
        "command",
        "exit_code",
        "status",
        "artifact",
        "artifact_sha256",
        "previous_record_sha256",
        "record_sha256",
    }
    for index, record in enumerate(records, 1):
        missing = sorted(required - set(record))
        if missing:
            errors.append(f"record {index}: missing fields {', '.join(missing)}")
            continue
        if record["sequence"] != index:
            errors.append(f"record {index}: invalid sequence {record['sequence']!r}")
        if record["previous_record_sha256"] != previous_hash:
            errors.append(f"record {index}: previous hash does not match")
        claimed_hash = record["record_sha256"]
        payload = {key: value for key, value in record.items() if key != "record_sha256"}
        actual_hash = _record_hash(payload)
        if claimed_hash != actual_hash:
            errors.append(f"record {index}: record hash does not match")
        if check_artifacts:
            artifact = Path(record["artifact"])
            if not artifact.is_file():
                errors.append(f"record {index}: artifact not found: {artifact}")
            elif sha256_file(artifact) != record["artifact_sha256"]:
                errors.append(f"record {index}: artifact hash does not match")
        previous_hash = claimed_hash
    return {
        "status": "PASS" if records and not errors else "FAIL",
        "records": len(records),
        "head_sha256": previous_hash,
        "errors": errors or ([] if records else ["ledger contains no evidence records"]),
    }
