"""Output of git, quality gates and verifiers is read as UTF-8 on every platform.

Each was read with the locale's default encoding. On Windows that is a legacy code
page: UTF-8 text came back garbled, and a byte the code page cannot map made the read
fail, so `integrity` crashed on such a diff instead of auditing it. On any platform a
byte that is not valid UTF-8 made the read fail the same way. Each case feeds real
non-ASCII and invalid bytes through the real subprocess.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from agentic_discipline.bootstrap import initialize_project
from agentic_discipline.common import run_git
from agentic_discipline.quality import run_gate
from agentic_discipline.verifier.executor import execute_verifier
from agentic_discipline.verifier.registry import register_verifier

# UTF-8 text with characters outside every legacy code page, then a lone Latin-1 byte
# that is not valid UTF-8.
TEXT = "café → 中文 Đ"
BYTES = TEXT.encode("utf-8") + b" caf\xe9\n"
DECODED = f"{TEXT} caf�\n"

PRINT_BYTES = f"import sys; sys.stdout.buffer.write({BYTES!r})"


def test_git_output_is_decoded_as_utf8_with_invalid_bytes_replaced(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "notes.txt").write_bytes(BYTES)
    subprocess.run(["git", "add", "notes.txt"], cwd=tmp_path, check=True)

    diff = run_git(["diff", "--cached", "--unified=0"], cwd=tmp_path)

    assert f"+{DECODED}" in diff


def test_quality_gate_output_is_decoded_as_utf8_with_invalid_bytes_replaced(
    tmp_path: Path,
) -> None:
    result = run_gate(
        {"name": "encoding", "command": [sys.executable, "-c", PRINT_BYTES]}, tmp_path
    )

    assert result.status == "PASS"
    assert result.stdout == DECODED


def test_verifier_output_is_decoded_as_utf8_with_invalid_bytes_replaced(tmp_path: Path) -> None:
    project = tmp_path / "project"
    initialize_project(project)
    source = tmp_path / "source"
    source.mkdir()
    contract = {
        "schema_version": "1",
        "id": "VER-ENCODING",
        "name": "encoding",
        "requirement_ids": ["REQ-ENCODING"],
        "claim": "verifier output survives any bytes",
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
    (source / "verifier.json").write_text(json.dumps(contract), encoding="utf-8")
    (source / "run.py").write_text(PRINT_BYTES + "\n", encoding="utf-8")
    register_verifier(source, project)

    result = execute_verifier(project, "VER-ENCODING")

    assert result["status"] == "PASS"
    assert result["observations"]["stdout"] == DECODED
