"""A machine with no git on PATH: stock containers and minimal servers.

Adoption works without git (it walks the tree instead of asking `git ls-files`), but the
probes it made on the way still started `git` and let the missing executable surface as
`OPERATION_FAILED: [Errno 2] No such file or directory: 'git'`. These tests take git off
PATH for real, so every subprocess the kit starts sees what such a machine shows it.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

from agentic_discipline import common
from agentic_discipline.bootstrap import initialize_project
from agentic_discipline.common import AgenticError, GitUnavailableError, run_git
from agentic_discipline.control import cli, discovery
from agentic_discipline.control.plane import Plane


@pytest.fixture
def no_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    empty = tmp_path / "empty-path"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    assert shutil.which("git") is None
    project = tmp_path / "project"
    project.mkdir()
    (project / "app.py").write_text("value = 1\n", encoding="utf-8")
    return project


def test_adopt_on_the_command_line_succeeds_without_git(
    no_git: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["agentic", "adopt", str(no_git), "--json"])
    cli.main()
    payload = json.loads(capsys.readouterr().out)
    assert "code" not in payload, payload
    assert payload["data"]["adopted"] is True
    with Plane(no_git) as plane:
        assert plane.store.audit()["status"] == "PASS"


def test_init_adopts_without_git_and_names_git_as_the_gap(no_git: Path) -> None:
    result = initialize_project(no_git)
    assert result["control"]["status"] == "ADOPTED"
    git = next(c for c in result["readiness"]["checks"] if c["name"] == "git_integration")
    assert (git["status"], git["detail"]) == ("FAIL", "git is not installed")


def test_the_discovery_probe_reads_a_missing_git_as_no_answer(no_git: Path) -> None:
    assert discovery.git(no_git, ["rev-parse", "HEAD"]) == ""
    assert discovery.files(no_git) == [Path("app.py")]


def test_an_operation_that_needs_git_says_to_install_it(no_git: Path) -> None:
    with pytest.raises(GitUnavailableError) as caught:
        run_git(["rev-parse", "HEAD"], cwd=no_git)
    error = caught.value
    assert str(error) == (
        "git is not installed or not on PATH; install git and run the command again"
    )
    assert error.code == "NOT_READY"
    # Callers that caught either family before still catch it.
    assert isinstance(error, AgenticError)
    assert isinstance(error, OSError)


def test_a_missing_working_directory_is_not_reported_as_missing_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Git counts as installed whatever this machine has, so the test always runs the branch
    # that must re-raise. POSIX raises FileNotFoundError for a missing cwd, the same type as a missing
    # executable; Windows raises NotADirectoryError. Neither may be relabelled.
    monkeypatch.setattr(common.shutil, "which", lambda name, *_a, **_k: f"/usr/bin/{name}")
    assert common.git_installed()
    gone = tmp_path / "gone"
    with pytest.raises(OSError) as caught:
        run_git(["status"], cwd=gone)
    assert not isinstance(caught.value, GitUnavailableError)
    with pytest.raises(OSError):
        discovery.git(gone, ["status"])
