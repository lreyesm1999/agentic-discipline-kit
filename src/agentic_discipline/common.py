from __future__ import annotations

import subprocess
from pathlib import Path


class AgenticError(RuntimeError):
    """Base error for deterministic Agentic Discipline tooling."""


def run_git(args: list[str], cwd: Path | None = None) -> str:
    process = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if process.returncode != 0:
        raise AgenticError(process.stderr.strip() or "git command failed")
    return process.stdout


def changed_files(base_ref: str, cwd: Path | None = None) -> list[str]:
    output = run_git(["diff", "--name-only", base_ref, "--"], cwd=cwd)
    return [line.strip() for line in output.splitlines() if line.strip()]
