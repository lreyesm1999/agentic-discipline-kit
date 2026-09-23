"""Command entry points pass on what they were asked, from where they were asked.

`adapters sync --dry-run` must reach the synchroniser, `doctor` must judge the project
it found rather than whatever repository the shell happens to be in, `init` must not
install the kit into the kit, and the constitution drops exactly its own title line.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from agentic_discipline import bootstrap, cli
from agentic_discipline.adapters import _rules
from agentic_discipline.bootstrap import initialize_project
from agentic_discipline.common import AgenticError, run_git


def test_adapters_sync_dry_run_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = argparse.Namespace(project_root=str(tmp_path), adapter=[], dry_run=True, json=True)

    assert cli.command_adapters_sync(args) == 0

    assert json.loads(capsys.readouterr().out)["dry_run"] is True
    assert list(tmp_path.iterdir()) == []


def test_doctor_asks_git_about_the_project_not_the_current_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    initialize_project(root)
    nested = root / "vendor" / "lib"
    nested.mkdir(parents=True)
    run_git(["init", "-q"], cwd=nested)
    monkeypatch.chdir(nested)

    cli.command_doctor(argparse.Namespace(json=True, fast=False))

    assert json.loads(capsys.readouterr().out)["git_worktree"] is False


def test_init_refuses_the_kit_root_it_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kit = tmp_path / "kit"
    kit.mkdir()
    monkeypatch.setattr(bootstrap, "find_contract_root", lambda: kit)

    with pytest.raises(AgenticError) as caught:
        initialize_project(kit, dry_run=True)
    assert str(caught.value) == "refusing to bootstrap the kit into itself"


def test_the_constitution_loses_only_its_title_line() -> None:
    assert _rules("# Core\nFirst rule.\nSecond rule.\n") == "First rule.\nSecond rule."
    assert _rules("First rule.\n") == "First rule."
