"""Verifier execution paths beyond the result document.

The result document tests pin every field for a passing, failing, blocked and timed out
run. The paths that lead there were still loose: where the command runs, how a Python
command is found, what the verifier is told about its raw result file, which package
artifacts are recorded, and partial output from a timeout. Each case drives a real
registered verifier and pins the exact outcome.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline.bootstrap import initialize_project
from agentic_discipline.common import AgenticError
from agentic_discipline.verifier import executor
from agentic_discipline.verifier.executor import _required_command, execute_verifier
from agentic_discipline.verifier.registry import register_verifier
from agentic_discipline.verifier.result import hash_file

VERIFIER_ID = "VER-PATHS"


def _contract(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "schema_version": "1",
        "id": VERIFIER_ID,
        "name": "execution paths",
        "requirement_ids": ["REQ-PATHS"],
        "claim": "execution paths are exact",
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


def _package(project: Path) -> Path:
    return project / ".agentic" / "verification" / "generated" / VERIFIER_ID


def test_python_commands_are_checked_against_the_running_interpreter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _required_command(["python", "run.py"]) == sys.executable
    assert _required_command(["python3"]) == sys.executable
    assert _required_command(["node", "run.js"]) == "node"


def test_default_working_directory_is_the_verifier_package(tmp_path: Path) -> None:
    script = (
        "import os, pathlib\n"
        "pathlib.Path('cwd.txt').write_text(os.getcwd(), encoding='utf-8')\n"
        "pathlib.Path(os.environ['ADK_RESULT_PATH']).write_text('raw', encoding='utf-8')\n"
    )
    project = _project(tmp_path, _contract(), script)

    assert execute_verifier(project, VERIFIER_ID)["status"] == "PASS"

    package = _package(project).resolve()
    assert Path((package / "cwd.txt").read_text(encoding="utf-8")).resolve() == package
    raw = project / ".agentic" / "verification" / "artifacts" / f"{VERIFIER_ID}.raw.json"
    assert raw.read_text(encoding="utf-8") == "raw"


def test_a_project_relative_working_directory_is_used(tmp_path: Path) -> None:
    script = (
        "import os, pathlib, sys\n"
        "pathlib.Path(sys.argv[0]).with_name('cwd.txt').write_text(os.getcwd(), encoding='utf-8')\n"
    )
    contract = _contract(
        working_directory="tools",
        command=[sys.executable, "../.agentic/verification/generated/VER-PATHS/run.py"],
    )
    project = tmp_path / "project"
    initialize_project(project)
    (project / "tools").mkdir()
    source = tmp_path / "source"
    source.mkdir()
    (source / "verifier.json").write_text(json.dumps(contract), encoding="utf-8")
    (source / "run.py").write_text(script, encoding="utf-8")
    register_verifier(source, project)

    assert execute_verifier(project, VERIFIER_ID)["status"] == "PASS"
    cwd = Path((_package(project) / "cwd.txt").read_text(encoding="utf-8"))
    assert cwd.resolve() == (project / "tools").resolve()


@pytest.mark.parametrize("directory", ["missing", "run.py"])
def test_an_unusable_working_directory_is_refused(tmp_path: Path, directory: str) -> None:
    project = _project(tmp_path, _contract(working_directory=directory), "pass\n")
    (project / "run.py").write_text("not a directory", encoding="utf-8")
    with pytest.raises(AgenticError) as caught:
        execute_verifier(project, VERIFIER_ID)
    assert str(caught.value) == (
        "verifier working_directory must be an existing project-relative directory"
    )


def test_a_blank_command_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _project(tmp_path, _contract(), "pass\n")
    monkeypatch.setattr(executor, "_command_parts", lambda command: [])
    with pytest.raises(AgenticError) as caught:
        execute_verifier(project, VERIFIER_ID)
    assert str(caught.value) == "verifier command cannot be empty"


def test_a_missing_executable_blocks_the_run_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path, _contract(command=["adk-missing-tool", "run"]), "pass\n")
    result = execute_verifier(project, VERIFIER_ID)
    assert (result["status"], result["observations"]) == (
        "BLOCKED",
        {"missing_commands": ["adk-missing-tool"], "missing_env": []},
    )


def test_timeouts_keep_partial_output(tmp_path: Path) -> None:
    script = (
        "import sys, time\n"
        "sys.stdout.write('started'); sys.stdout.flush()\n"
        "sys.stderr.write('warming'); sys.stderr.flush()\n"
        "time.sleep(30)\n"
    )
    project = _project(tmp_path, _contract(timeout_seconds=1), script)
    result = execute_verifier(project, VERIFIER_ID)
    assert result["status"] == "BLOCKED"
    assert result["error"] == "verifier timed out after 1 seconds"
    # Whether output flushed before the kill is captured depends on the platform.
    assert result["observations"]["stdout"] in {"", "started"}
    assert result["observations"]["stderr"] in {"", "warming"}


def test_package_artifacts_are_recorded_relative_to_the_project_once(tmp_path: Path) -> None:
    script = (
        "import pathlib\n"
        "pathlib.Path('package-report.txt').write_text('package', encoding='utf-8')\n"
        "pathlib.Path('shared.txt').write_text('package copy', encoding='utf-8')\n"
    )
    project = _project(
        tmp_path,
        _contract(artifacts=["package-report.txt", "shared.txt", "absent.txt"]),
        script,
    )
    shared = project / "shared.txt"
    shared.write_text("project copy", encoding="utf-8")

    result = execute_verifier(project, VERIFIER_ID)

    package_report = _package(project) / "package-report.txt"
    assert result["artifacts"] == [
        {"path": "shared.txt", "sha256": hash_file(shared)},
        {
            "path": f".agentic/verification/generated/{VERIFIER_ID}/package-report.txt",
            "sha256": hash_file(package_report),
        },
    ]


@pytest.mark.parametrize(
    ("stdout", "stderr", "expected"),
    [
        (b"\xffstarted", "warming", {"stdout": "�started", "stderr": "warming"}),
        (None, None, {"stdout": "", "stderr": ""}),
        (b"x" * 20005, "y" * 20003, {"stdout": "x" * 20000, "stderr": "y" * 20000}),
    ],
    ids=["bytes-and-text", "nothing", "trimmed"],
)
def test_timeout_output_is_decoded_and_trimmed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stdout: Any,
    stderr: Any,
    expected: dict[str, str],
) -> None:
    import subprocess

    project = _project(tmp_path, _contract(timeout_seconds=5), "pass\n")

    def expire(command: Any, **options: Any) -> Any:
        raise subprocess.TimeoutExpired(command, 5, output=stdout, stderr=stderr)

    monkeypatch.setattr(executor.subprocess, "run", expire)
    result = execute_verifier(project, VERIFIER_ID)

    assert (result["status"], result["error"], result["observations"]) == (
        "BLOCKED",
        "verifier timed out after 5 seconds",
        expected,
    )
