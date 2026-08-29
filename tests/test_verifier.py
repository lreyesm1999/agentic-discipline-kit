import json
from pathlib import Path

from agentic_discipline.bootstrap import initialize_project
from agentic_discipline.verifier.executor import execute_verifier
from agentic_discipline.verifier.registry import list_verifiers, register_verifier


def _contract(path: Path, *, command: list[str] | None = None, requires: dict | None = None) -> None:
    path.mkdir()
    (path / "verifier.json").write_text(
        json.dumps(
            {
                "schema_version": "1",
                "id": "VER-SMOKE",
                "name": "smoke verifier",
                "requirement_ids": ["REQ-001"],
                "claim": "The smoke command succeeds",
                "type": "custom",
                "origin": "handwritten",
                "risk": "LOW",
                "command": command or ["python", "run.py"],
                "timeout_seconds": 10,
                "working_directory": ".",
                "expected_exit_code": 0,
                "artifacts": [],
                "requires": requires or {},
                "sensitivity": {"method": "known_bad_fixture", "status": "UNPROVEN"},
                "persistence": "durable",
                "protected": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (path / "run.py").write_text("raise SystemExit(0)\n", encoding="utf-8")


def test_register_and_execute_verifier_records_result(tmp_path: Path) -> None:
    project = tmp_path / "project"
    initialize_project(project)
    source = tmp_path / "source"
    _contract(source)

    entry = register_verifier(source, project)
    assert entry["id"] == "VER-SMOKE"
    assert list_verifiers(project)[0]["trust"] == "DRAFT"

    result = execute_verifier(project, "VER-SMOKE")
    assert result["status"] == "PASS"
    assert result["exit_code"] == 0
    assert (project / "artifacts" / "evidence-ledger.jsonl").is_file()


def test_missing_dependency_is_blocked(tmp_path: Path) -> None:
    project = tmp_path / "project"
    initialize_project(project)
    source = tmp_path / "source"
    _contract(source, requires={"commands": ["definitely-not-installed-adk-command"]})
    register_verifier(source, project)

    result = execute_verifier(project, "VER-SMOKE")
    assert result["status"] == "BLOCKED"
    assert result["exit_code"] is None
