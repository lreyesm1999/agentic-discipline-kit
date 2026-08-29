import json
from pathlib import Path

import pytest

from agentic_discipline.adapters import sync_adapters
from agentic_discipline.bootstrap import initialize_project
from agentic_discipline.common import AgenticError
from agentic_discipline.evolution import hygiene, register_lifecycle
from agentic_discipline.migration import migrate_to_v3
from agentic_discipline.verifier.protection import protect_verifier
from agentic_discipline.verifier.registry import load_verifier, register_verifier


def _validated_verifier(path: Path) -> None:
    path.mkdir()
    (path / "verifier.json").write_text(
        json.dumps(
            {
                "schema_version": "1",
                "id": "VER-PROTECTED",
                "name": "protected smoke",
                "requirement_ids": ["REQ-1"],
                "claim": "The protected smoke verifier succeeds",
                "type": "custom",
                "origin": "generated",
                "risk": "STANDARD",
                "command": ["python", "run.py"],
                "timeout_seconds": 10,
                "working_directory": ".",
                "expected_exit_code": 0,
                "sensitivity": {"method": "known_bad_fixture", "evidence": "sensitivity.json", "status": "PROVEN"},
                "persistence": "durable",
                "protected": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (path / "run.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    (path / "sensitivity.json").write_text('{"status":"FAIL"}\n', encoding="utf-8")


def test_adapter_sync_is_idempotent_and_migration_is_reported(tmp_path: Path) -> None:
    project = tmp_path / "project"
    initialize_project(project)
    assert (project / ".agentic" / "schemas" / "evidence.schema.json").is_file()
    assert (project / ".agentic" / "schemas" / "verification-plan.schema.json").is_file()
    (project / ".claude").mkdir()
    first = sync_adapters(project)
    second = sync_adapters(project)
    assert "claude" in first["adapters"]
    assert all(str(item).startswith("SKIP") for item in second["actions"] if "SKILL" not in str(item))
    report = migrate_to_v3(project)
    assert report["to"] == "3.0"
    assert (project / "artifacts" / "migration-v3-report.json").is_file()


def test_protected_verifier_change_is_rejected(tmp_path: Path) -> None:
    project = tmp_path / "project"
    initialize_project(project)
    source = tmp_path / "source"
    _validated_verifier(source)
    register_verifier(source, project)
    protect_verifier(project, "VER-PROTECTED")
    metadata = project / ".agentic" / "verification" / "generated" / "VER-PROTECTED" / "verifier.json"
    metadata.write_text(metadata.read_text(encoding="utf-8").replace("protected smoke", "changed"), encoding="utf-8")
    with pytest.raises(AgenticError, match="protected verifier changed"):
        load_verifier(project, "VER-PROTECTED")


def test_hygiene_reports_unresolved_lifecycle_items(tmp_path: Path) -> None:
    project = tmp_path / "project"
    initialize_project(project)
    (project / "debug_probe.py").write_text("pass\n", encoding="utf-8")
    register_lifecycle(project, {"id": "TMP-1", "path": "debug_probe.py", "state": "REMOVE"})
    result = hygiene(project)
    assert result["status"] == "FAIL"
    assert "TMP-1" in result["unresolved_removals"]
