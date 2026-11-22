from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class AgenticError(RuntimeError):
    """Base error for deterministic Agentic Discipline tooling."""


class GitUnavailableError(AgenticError, FileNotFoundError):
    """Git is not installed or not on PATH, for an operation that cannot run without it.

    Still a FileNotFoundError, which is what callers caught before, so the control command
    line and MCP server keep answering with an error payload rather than a traceback, now
    with a code and a sentence that says what to do.
    """

    # The code the versioned API documents for work that needs git.
    code = "NOT_READY"


GIT_UNAVAILABLE = "git is not installed or not on PATH; install git and run the command again"


def git_installed() -> bool:
    return shutil.which("git") is not None


def run_git(args: list[str], cwd: Path | None = None) -> str:
    try:
        process = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=False,
            capture_output=True,
            # Git writes UTF-8. The locale default is a legacy code page on Windows, where a
            # diff containing a byte it cannot map would stop the gate reading it at all.
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        # A missing working directory raises the same error; only a missing git is this one.
        if git_installed():
            raise
        raise GitUnavailableError(GIT_UNAVAILABLE) from exc
    if process.returncode != 0:
        raise AgenticError(process.stderr.strip() or "git command failed")
    return process.stdout


def changed_files(base_ref: str, cwd: Path | None = None) -> list[str]:
    output = run_git(["diff", "--name-only", base_ref, "--"], cwd=cwd)
    return [line.strip() for line in output.splitlines() if line.strip()]
