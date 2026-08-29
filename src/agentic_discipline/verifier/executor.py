from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..common import AgenticError
from ..evidence import append_evidence
from .registry import load_verifier, verification_root
from .result import artifact_hashes, hash_file
from .sensitivity import sensitivity_status


def _command_parts(command: str | list[str]) -> list[str]:
    if isinstance(command, list):
        return command
    return shlex.split(command, posix=os.name != "nt")


def _required_command(parts: list[str]) -> str:
    executable = parts[0]
    if executable in {"python", "python3"}:
        return sys.executable
    return executable


def _safe_working_directory(project_root: Path, relative: str) -> Path:
    root = project_root.resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_dir():
        raise AgenticError("verifier working_directory must be an existing project-relative directory")
    return path


def execute_verifier(project_root: Path, verifier_id: str) -> dict[str, Any]:
    project_root = project_root.resolve()
    metadata, directory = load_verifier(project_root, verifier_id)
    sensitivity_status(metadata, project_root, directory)
    parts = _command_parts(metadata["command"])
    if not parts:
        raise AgenticError("verifier command cannot be empty")
    required = metadata.get("requires", {})
    missing = [name for name in required.get("commands", []) if shutil.which(name) is None]
    if shutil.which(_required_command(parts)) is None:
        missing.append(parts[0])
    missing_env = [name for name in required.get("env", []) if not os.environ.get(name)]
    started = datetime.now(timezone.utc)
    start_clock = time.monotonic()
    result: dict[str, Any] = {
        "schema_version": "1",
        "verification_id": verifier_id,
        "status": "BLOCKED" if missing or missing_env else "UNKNOWN",
        "started_at": started.isoformat(),
        "finished_at": started.isoformat(),
        "command": shlex.join(parts),
        "exit_code": None,
        "duration_seconds": 0.0,
        "observations": {"missing_commands": missing, "missing_env": missing_env},
        "artifacts": [],
        "toolchain": {"python": sys.version.split()[0]},
        "environment": {"cwd": str(project_root)},
        "hashes": {},
    }
    if not missing and not missing_env:
        working_directory = str(metadata.get("working_directory", "."))
        # A verifier package is self-contained by default, so `python run.py`
        # resolves beside verifier.json.  Set an explicit project-relative
        # directory when the verifier intentionally operates from the project.
        cwd = directory if working_directory == "." else _safe_working_directory(project_root, working_directory)
        env = os.environ.copy()
        result_path = verification_root(project_root) / "artifacts" / f"{verifier_id}.raw.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        env["ADK_RESULT_PATH"] = str(result_path)
        try:
            completed = subprocess.run(
                parts,
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=float(metadata["timeout_seconds"]),
                check=False,
            )
            result["exit_code"] = completed.returncode
            result["observations"] = {
                "stdout": completed.stdout[-20000:],
                "stderr": completed.stderr[-20000:],
            }
            expected = int(metadata.get("expected_exit_code", 0))
            result["status"] = "PASS" if completed.returncode == expected else "FAIL"
        except subprocess.TimeoutExpired as exc:
            result["status"] = "BLOCKED"
            result["error"] = f"verifier timed out after {metadata['timeout_seconds']} seconds"
            result["observations"] = {"stdout": str(exc.stdout or ""), "stderr": str(exc.stderr or "")}
    result["duration_seconds"] = round(time.monotonic() - start_clock, 6)
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    result["artifacts"] = artifact_hashes(project_root, metadata.get("artifacts", []))
    seen_artifacts = {item["path"] for item in result["artifacts"]}
    for relative in metadata.get("artifacts", []):
        package_path = (directory / relative).resolve()
        if package_path.is_file() and package_path.is_relative_to(project_root) and relative not in seen_artifacts:
            result["artifacts"].append(
                {"path": package_path.relative_to(project_root).as_posix(), "sha256": hash_file(package_path)}
            )
    output = verification_root(project_root) / "artifacts" / f"{verifier_id}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    result["hashes"]["result"] = _file_hash(output)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if result["status"] in {"PASS", "FAIL"}:
        append_evidence(
            project_root / "artifacts" / "evidence-ledger.jsonl",
            output,
            tool=f"verifier:{verifier_id}",
            command=result["command"],
            exit_code=0 if result["status"] == "PASS" else 1,
        )
    return result


def _file_hash(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()
