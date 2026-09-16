"""The verifier result document, pinned field by field.

Earlier tests only read ``status`` from the result, so the recorded timestamps,
duration, observations, artifact hashes, self-hash and ledger record could all be
wrong without a failure. Here the executor's clock is fixed, so every field of the
result, of the JSON written to disk and of the evidence record has an exact value.
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import sys
from collections.abc import Iterator
from datetime import datetime, tzinfo
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from agentic_discipline.bootstrap import initialize_project
from agentic_discipline.common import AgenticError
from agentic_discipline.verifier import executor
from agentic_discipline.verifier.executor import _command_parts, execute_verifier
from agentic_discipline.verifier.registry import register_verifier
from agentic_discipline.verifier.result import hash_file

VERIFIER_ID = "VER-RESULT"
STARTED = "2026-01-02T03:04:05+00:00"
FINISHED = "2026-01-02T03:04:06+00:00"


class _FixedDateTime:
    """Stands in for ``datetime`` inside the executor; honours the requested zone."""

    def __init__(self) -> None:
        self._moments: Iterator[datetime] = iter(
            [datetime(2026, 1, 2, 3, 4, 5), datetime(2026, 1, 2, 3, 4, 6)]
        )

    def now(self, tz: tzinfo | None = None) -> datetime:
        return next(self._moments).replace(tzinfo=tz)


@pytest.fixture
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(executor, "datetime", _FixedDateTime())
    monotonic = iter([10.0, 11.23456789])
    monkeypatch.setattr(executor, "time", SimpleNamespace(monotonic=lambda: next(monotonic)))


def _contract(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "schema_version": "1",
        "id": VERIFIER_ID,
        "name": "result contract",
        "requirement_ids": ["REQ-RESULT"],
        "claim": "the result document is exact",
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
    data.update(overrides)
    return {key: value for key, value in data.items() if value is not None}


def _project(tmp_path: Path, contract: dict[str, Any], script: str) -> Path:
    project = tmp_path / "project"
    initialize_project(project)
    source = tmp_path / "source"
    source.mkdir()
    (source / "verifier.json").write_text(json.dumps(contract, indent=2), encoding="utf-8")
    (source / "run.py").write_text(script, encoding="utf-8")
    register_verifier(source, project)
    return project


def _result_file(project: Path) -> Path:
    return project / ".agentic" / "verification" / "artifacts" / f"{VERIFIER_ID}.json"


def _ledger(project: Path) -> Path:
    return project / "artifacts" / "evidence-ledger.jsonl"


def _assert_written_and_self_hashed(project: Path, result: dict[str, Any]) -> None:
    output = _result_file(project)
    assert output.read_text(encoding="utf-8") == json.dumps(result, indent=2) + "\n"
    # The self-hash covers the document as first written, before the hash was added.
    first_write = json.dumps({**result, "hashes": {}}, indent=2) + "\n"
    first_bytes = first_write.replace("\n", os.linesep).encode("utf-8")
    assert result["hashes"] == {"result": hashlib.sha256(first_bytes).hexdigest()}


def _ledger_records(project: Path) -> list[dict[str, Any]]:
    lines = _ledger(project).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def test_completed_run_records_every_result_field(tmp_path: Path, fixed_clock: None) -> None:
    script = (
        "import sys\n"
        "sys.stdout.write('x' * 5000 + 'y' * 20000)\n"
        "sys.stderr.write('p' * 5000 + 'q' * 20000)\n"
        "raise SystemExit(3)\n"
    )
    project = _project(tmp_path, _contract(expected_exit_code=3, artifacts=["report.txt"]), script)
    report = project / "report.txt"
    report.write_text("report\n", encoding="utf-8")

    result = execute_verifier(project, VERIFIER_ID)

    assert {key: value for key, value in result.items() if key != "hashes"} == {
        "schema_version": "1",
        "verification_id": VERIFIER_ID,
        "status": "PASS",
        "started_at": STARTED,
        "finished_at": FINISHED,
        "command": shlex.join([sys.executable, "run.py"]),
        "exit_code": 3,
        "duration_seconds": 1.234568,
        "observations": {"stdout": "y" * 20000, "stderr": "q" * 20000},
        "artifacts": [{"path": "report.txt", "sha256": hash_file(report)}],
        "toolchain": {"python": sys.version.split()[0]},
        "environment": {"cwd": str(project.resolve())},
    }
    _assert_written_and_self_hashed(project, result)
    [record] = _ledger_records(project)
    assert (record["tool"], record["command"], record["exit_code"], record["status"]) == (
        f"verifier:{VERIFIER_ID}",
        result["command"],
        0,
        "PASS",
    )
    assert record["artifact"] == str(_result_file(project).resolve())


def test_unexpected_exit_code_is_recorded_as_a_failed_ledger_entry(tmp_path: Path) -> None:
    project = _project(tmp_path, _contract(), "raise SystemExit(3)\n")

    result = execute_verifier(project, VERIFIER_ID)

    assert (result["status"], result["exit_code"]) == ("FAIL", 3)
    [record] = _ledger_records(project)
    assert (record["exit_code"], record["status"]) == (1, "FAIL")


def test_blocked_run_keeps_its_initial_fields_and_writes_no_evidence(
    tmp_path: Path, fixed_clock: None
) -> None:
    missing = "definitely-not-installed-adk-command"
    project = _project(tmp_path, _contract(requires={"commands": [missing]}), "pass\n")

    result = execute_verifier(project, VERIFIER_ID)

    assert {key: value for key, value in result.items() if key != "hashes"} == {
        "schema_version": "1",
        "verification_id": VERIFIER_ID,
        "status": "BLOCKED",
        "started_at": STARTED,
        "finished_at": FINISHED,
        "command": shlex.join([sys.executable, "run.py"]),
        "exit_code": None,
        "duration_seconds": 1.234568,
        "observations": {"missing_commands": [missing], "missing_env": []},
        "artifacts": [],
        "toolchain": {"python": sys.version.split()[0]},
        "environment": {"cwd": str(project.resolve())},
    }
    _assert_written_and_self_hashed(project, result)
    assert not _ledger(project).exists()


def test_timed_out_run_reports_the_limit_and_empty_output(tmp_path: Path) -> None:
    project = _project(tmp_path, _contract(timeout_seconds=0.5), "import time\ntime.sleep(30)\n")

    result = execute_verifier(project, VERIFIER_ID)

    assert result["status"] == "BLOCKED"
    assert result["exit_code"] is None
    assert result["error"] == "verifier timed out after 0.5 seconds"
    assert result["observations"] == {"stdout": "", "stderr": ""}
    _assert_written_and_self_hashed(project, result)
    assert not _ledger(project).exists()


def test_contract_without_artifacts_records_none(tmp_path: Path) -> None:
    project = _project(tmp_path, _contract(artifacts=None), "pass\n")
    result = execute_verifier(project, VERIFIER_ID)
    assert (result["status"], result["artifacts"]) == ("PASS", [])


def test_proven_verifier_finds_its_evidence_in_the_package(tmp_path: Path) -> None:
    proven = {"method": "negative_control", "status": "PROVEN", "evidence": "proof.json"}
    project = tmp_path / "project"
    initialize_project(project)
    source = tmp_path / "source"
    source.mkdir()
    (source / "verifier.json").write_text(json.dumps(_contract(sensitivity=proven)), "utf-8")
    (source / "run.py").write_text("pass\n", encoding="utf-8")
    (source / "proof.json").write_text("{}\n", encoding="utf-8")
    register_verifier(source, project)

    assert execute_verifier(project, VERIFIER_ID)["status"] == "PASS"
    generated = project / ".agentic" / "verification" / "generated" / VERIFIER_ID
    (generated / "proof.json").unlink()
    with pytest.raises(AgenticError, match="sensitivity evidence not found: proof.json"):
        execute_verifier(project, VERIFIER_ID)


def test_string_command_is_split_with_the_platform_quoting_rules() -> None:
    parts = _command_parts('tool --name "two words"')
    if os.name == "nt":
        assert parts == ["tool", "--name", '"two words"']
    else:
        assert parts == ["tool", "--name", "two words"]


def test_hash_file_covers_content_larger_than_one_read_chunk(tmp_path: Path) -> None:
    payload = bytes(range(256)) * 600
    artifact = tmp_path / "large.bin"
    artifact.write_bytes(payload)
    assert hash_file(artifact) == hashlib.sha256(payload).hexdigest()
