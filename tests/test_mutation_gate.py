"""The CI mutation step must fail on survivor, timeout and missing evidence."""

import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

GATE_SCRIPT = next(
    parent / "scripts" / "mutation_gate.py"
    for parent in Path(__file__).resolve().parents
    if (parent / "scripts" / "mutation_gate.py").is_file()
)
gate = runpy.run_path(str(GATE_SCRIPT))["gate"]


@pytest.fixture
def complete_report():
    return {
        "total": 10,
        "killed": 10,
        "survived": 0,
        "timeout": 0,
        "no_tests": 0,
        "skipped": 0,
        "suspicious": 0,
        "check_was_interrupted_by_user": 0,
        "segfault": 0,
    }


def test_enforces_mutation_outcome_and_invalid_data(complete_report):
    assert gate(complete_report)["status"] == "PASS"
    for field in ("survived", "timeout", "no_tests", "skipped", "suspicious", "segfault"):
        report = {**complete_report, "killed": 9, field: 1}
        assert gate(report)["status"] == "FAIL"
    for invalid in (
        {},
        {**complete_report, "total": 0},
        {**complete_report, "killed": True},
        {**complete_report, "total": 100, "killed": 1},
        {**complete_report, "caught_by_type_check": 1},
    ):
        assert gate(invalid)["status"] == "FAIL"


def test_command_exits_nonzero_for_actual_survivors(tmp_path: Path, complete_report):
    path = tmp_path / "mutation-stats.json"
    path.write_text(json.dumps({**complete_report, "killed": 9, "survived": 1}))
    failed = subprocess.run(
        [sys.executable, str(GATE_SCRIPT), "--report", str(path)],
        capture_output=True,
        text=True,
    )
    assert failed.returncode == 1
    assert json.loads(failed.stdout)["unresolved"] == {"survived": 1}
    path.write_text(json.dumps(complete_report))
    passed = subprocess.run(
        [sys.executable, str(GATE_SCRIPT), "--report", str(path)],
        capture_output=True,
        text=True,
    )
    assert passed.returncode == 0
