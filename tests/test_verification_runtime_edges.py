import argparse
import json
import sys
from pathlib import Path

import pytest

from agentic_discipline import cli
from agentic_discipline.adapters import detect_adapters, sync_adapters
from agentic_discipline.bootstrap import initialize_project
from agentic_discipline.common import AgenticError
from agentic_discipline.evolution import hygiene, load_lifecycle, register_lifecycle
from agentic_discipline.verifier.executor import (
    _command_parts,
    _required_command,
    _safe_working_directory,
    execute_verifier,
)
from agentic_discipline.verifier.protection import check_protected_verifiers, protect_verifier
from agentic_discipline.verifier.registry import load_registry, load_verifier, register_verifier
from agentic_discipline.verifier.result import artifact_hashes, hash_file
from agentic_discipline.verifier.schema import validate_verifier
from agentic_discipline.verifier.sensitivity import sensitivity_status


def _write_contract(
    path: Path, verifier_id: str, *, command: list[str], **overrides: object
) -> None:
    path.mkdir()
    data: dict[str, object] = {
        "schema_version": "1",
        "id": verifier_id,
        "name": verifier_id,
        "requirement_ids": ["REQ-EDGE"],
        "claim": "edge behavior is verified",
        "type": "custom",
        "origin": "handwritten",
        "risk": "LOW",
        "command": command,
        "timeout_seconds": 10,
        "working_directory": ".",
        "expected_exit_code": 0,
        "artifacts": [],
        "sensitivity": {"method": "negative_control", "status": "UNPROVEN"},
        "persistence": "temporary",
        "protected": False,
    }
    data.update(overrides)
    (path / "verifier.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def test_executor_reports_fail_timeout_and_artifact_hash(tmp_path: Path) -> None:
    project = tmp_path / "project"
    initialize_project(project)

    failed = tmp_path / "failed"
    _write_contract(failed, "VER-FAIL", command=[sys.executable, "run.py"])
    (failed / "run.py").write_text("raise SystemExit(3)\n", encoding="utf-8")
    register_verifier(failed, project)
    assert execute_verifier(project, "VER-FAIL")["status"] == "FAIL"

    timed = tmp_path / "timed"
    _write_contract(timed, "VER-TIMEOUT", command=[sys.executable, "run.py"], timeout_seconds=0.1)
    (timed / "run.py").write_text("import time\ntime.sleep(2)\n", encoding="utf-8")
    register_verifier(timed, project)
    assert execute_verifier(project, "VER-TIMEOUT")["status"] == "BLOCKED"

    artifact = tmp_path / "artifact"
    _write_contract(
        artifact, "VER-ARTIFACT", command=[sys.executable, "run.py"], artifacts=["artifact.txt"]
    )
    (artifact / "run.py").write_text(
        "from pathlib import Path\nPath('artifact.txt').write_text('ok')\n", encoding="utf-8"
    )
    register_verifier(artifact, project)
    result = execute_verifier(project, "VER-ARTIFACT")
    assert result["artifacts"][0]["sha256"] == hash_file(
        project / ".agentic/verification/generated/VER-ARTIFACT/artifact.txt"
    )
    assert artifact_hashes(project, ["missing.txt"]) == []


def test_registry_and_sensitivity_error_paths(tmp_path: Path) -> None:
    project = tmp_path / "project"
    initialize_project(project)
    source = tmp_path / "source"
    _write_contract(source, "VER-DUP", command=[sys.executable, "run.py"])
    (source / "run.py").write_text("pass\n", encoding="utf-8")
    register_verifier(source, project)
    with pytest.raises(AgenticError, match="already registered"):
        register_verifier(source, project)
    with pytest.raises(AgenticError, match="verifier not found"):
        cli.command_verifier_inspect(
            argparse.Namespace(project_root=str(project), verifier_id="VER-NOPE")
        )
    assert load_registry(project)["schema_version"] == "1"
    with pytest.raises(AgenticError, match="evidence"):
        sensitivity_status(
            {"sensitivity": {"status": "PROVEN", "evidence": "missing.json"}},
            project,
            project,
        )


def test_verification_commands_and_adapters(tmp_path: Path) -> None:
    project = tmp_path / "project"
    initialize_project(project)
    (project / ".cursor").mkdir()
    (project / ".windsurf").mkdir()
    (project / ".github").mkdir()
    (project / "GEMINI.md").write_text("# Gemini\n", encoding="utf-8")
    assert cli.command_adapters_sync(argparse.Namespace(project_root=str(project), adapter=[])) == 0
    assert cli.command_verifier_list(argparse.Namespace(project_root=str(project))) == 0
    with pytest.raises(AgenticError, match="not found"):
        cli.command_verifier_validate(
            argparse.Namespace(
                project_root=str(project), verifier_id=None, path=str(project / "bad.json")
            )
        )
    assert cli.command_verify(argparse.Namespace(project_root=str(project), verifier_id=None)) == 0
    assert cli.command_hygiene(argparse.Namespace(project_root=str(project), base_ref=None)) == 0
    assert set(detect_adapters(project)) >= {"generic", "cursor", "windsurf", "copilot", "gemini"}


def test_evolution_registry_lifecycle_and_protection_scan(tmp_path: Path) -> None:
    project = tmp_path / "project"
    initialize_project(project)
    item = {"id": "TMP-EDGE", "path": "tmp.py", "state": "TEMPORARY"}
    assert register_lifecycle(project, item) == item
    assert load_lifecycle(project)["artifacts"][0]["id"] == "TMP-EDGE"
    assert check_protected_verifiers(project) == []


def test_verifier_helpers_cover_protocol_edges(tmp_path: Path) -> None:
    project = tmp_path / "project"
    initialize_project(project)
    assert _command_parts("echo hello") == ["echo", "hello"]
    assert _command_parts(["echo", "hello"]) == ["echo", "hello"]
    assert _required_command(["echo"]) == "echo"
    assert _required_command(["python", "-V"]) == sys.executable
    with pytest.raises(AgenticError, match="existing project"):
        _safe_working_directory(project, "missing")
    with pytest.raises(AgenticError, match="existing project"):
        _safe_working_directory(project, "../outside")
    assert validate_verifier({})
    assert sensitivity_status({"sensitivity": {"status": "UNPROVEN"}}, project, project) == "DRAFT"


def test_registry_invalid_and_protected_entries_are_rejected(tmp_path: Path) -> None:
    project = tmp_path / "project"
    initialize_project(project)
    registry = project / ".agentic" / "verification" / "registry.json"
    registry.write_text(
        '{"schema_version":"1","verifiers":[{"id":"VER-X","path":"../outside","trust":"DRAFT","persistence":"durable"}]}\n',
        encoding="utf-8",
    )
    with pytest.raises(AgenticError, match="escapes"):
        load_verifier(project, "VER-X")
    registry.write_text(
        '{"schema_version":"1","verifiers":[{"id":"VER-X","path":"missing","trust":"PROTECTED","persistence":"durable"}]}\n',
        encoding="utf-8",
    )
    assert check_protected_verifiers(project) == ["protected verifier missing: VER-X"]


def test_branch_edges_for_schema_sensitivity_and_protection(tmp_path: Path) -> None:
    project = tmp_path / "project"
    initialize_project(project)
    assert validate_verifier({"working_directory": "../escape"})
    assert validate_verifier({"protected": True, "sensitivity": {"status": "UNPROVEN"}})
    assert validate_verifier({"sensitivity": {"status": "PROVEN"}})

    root_evidence = project / "sensitivity.json"
    root_evidence.write_text("{}\n", encoding="utf-8")
    assert (
        sensitivity_status(
            {"sensitivity": {"status": "PROVEN", "evidence": "sensitivity.json"}}, project, project
        )
        == "VALIDATED"
    )
    verifier_dir = tmp_path / "verifier"
    verifier_dir.mkdir()
    (verifier_dir / "local.json").write_text("{}\n", encoding="utf-8")
    assert (
        sensitivity_status(
            {"sensitivity": {"status": "PROVEN", "evidence": "local.json"}}, project, verifier_dir
        )
        == "VALIDATED"
    )

    source = tmp_path / "proven"
    _write_contract(
        source,
        "VER-PROVEN-EDGE",
        command=[sys.executable, "run.py"],
        sensitivity={"method": "negative_control", "status": "PROVEN", "evidence": "proof.json"},
    )
    (source / "run.py").write_text("pass\n", encoding="utf-8")
    (source / "proof.json").write_text("{}\n", encoding="utf-8")
    register_verifier(source, project)
    protect_verifier(project, "VER-PROVEN-EDGE")
    assert check_protected_verifiers(project) == []
    metadata = (
        project / ".agentic" / "verification" / "generated" / "VER-PROVEN-EDGE" / "verifier.json"
    )
    metadata.write_text(metadata.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert check_protected_verifiers(project) == ["protected verifier changed: VER-PROVEN-EDGE"]
    with pytest.raises(AgenticError, match="not found"):
        protect_verifier(project, "VER-MISSING")

    registry = project / ".agentic" / "verification" / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "verifiers": [
                    {
                        "id": "VER-NOHASH",
                        "path": ".agentic/verification/generated/VER-PROVEN-EDGE",
                        "trust": "PROTECTED",
                        "persistence": "durable",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert check_protected_verifiers(project) == []


def test_cli_and_evolution_error_edges(tmp_path: Path) -> None:
    project = tmp_path / "project"
    initialize_project(project)
    source = tmp_path / "cli-verifier"
    _write_contract(source, "VER-CLI", command=[sys.executable, "run.py"])
    (source / "run.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    assert (
        cli.command_verifier_register(
            argparse.Namespace(path=str(source), project_root=str(project))
        )
        == 0
    )
    assert (
        cli.command_verify(argparse.Namespace(project_root=str(project), verifier_id="VER-CLI"))
        == 0
    )
    assert (
        cli.command_verifier_validate(
            argparse.Namespace(project_root=str(project), verifier_id="VER-CLI", path=None)
        )
        == 0
    )
    assert cli.command_doctor(
        argparse.Namespace(config=str(project / "agentic.config.json"), check_tools=True)
    ) in (0, 1)
    with pytest.raises(ValueError, match="unknown adapters"):
        sync_adapters(project, ["unknown"])
    with pytest.raises(AgenticError, match="only migration"):
        cli.command_migrate(argparse.Namespace(project_root=str(project), to="999.0", force=False))
    assert (
        cli.command_migrate(argparse.Namespace(project_root=str(project), to="3.0", force=False))
        == 0
    )
    with pytest.raises(AgenticError, match="requires"):
        register_lifecycle(project, {"id": "bad"})
    assert hygiene(project, "not-a-real-ref")["status"] == "PASS"
    lifecycle = project / ".agentic" / "evolution" / "lifecycle.json"
    lifecycle.parent.mkdir(parents=True, exist_ok=True)
    lifecycle.write_text("{}\n", encoding="utf-8")
    with pytest.raises(AgenticError, match="invalid evolution"):
        load_lifecycle(project)
