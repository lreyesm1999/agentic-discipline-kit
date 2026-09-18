import sys
from pathlib import Path

import pytest

from agentic_discipline.control.plane import Plane, adopt


@pytest.fixture
def project(tmp_path: Path):
    (tmp_path / "app.py").write_text("value = 1\n")
    (tmp_path / "test_app.py").write_text("import app\nassert app.value == 1\n")
    adopt(tmp_path)
    with Plane(tmp_path) as plane:
        yield plane


def contract():
    return {
        "objective": "Verify value",
        "scope": ["app.py", "test_app.py"],
        "out_of_scope": ["deployment"],
        "requirements": [],
        "acceptance": ["Value is one"],
        "dependencies": [],
        "boundaries": ["value API"],
        "context": [],
        "verification": [
            {"kind": "unit", "command": [sys.executable, "-B", "test_app.py"], "acceptance": [0]}
        ],
        "required_evidence": ["unit"],
        "rollback": "Revert app.py",
        "definition_of_done": "Current proof and checkpoint",
        "risk": "LOW",
        "budget": {
            "max_runtime": 30,
            "max_retries": 2,
            "max_files": 2,
            "max_lines": 100,
            "max_external_calls": 0,
            "max_cost": 0,
        },
    }


def checkpoint():
    return {
        "completed_work": ["local change"],
        "modified_files": ["app.py"],
        "commands_run": [],
        "tests_run": [],
        "test_results": [],
        "failures": [],
        "discoveries": [],
        "assumptions": [],
        "pending_issues": [],
        "current_hypothesis": "Tests establish acceptance",
        "next_action": "Verify then finish",
    }
