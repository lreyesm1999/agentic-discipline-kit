"""`migrate` and `hygiene` command decisions.

`migrate` must refuse unsupported targets before touching a project, and `hygiene`
turns the evolution report into the exit code CI gates on. Existing tests ran both
with real projects, so the target check, the forwarded options or the exit code could
change unnoticed. Each case records the call and the printed report.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline import cli
from agentic_discipline.common import AgenticError


@pytest.fixture
def printed(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    output: list[Any] = []
    monkeypatch.setattr(cli, "_json", output.append)
    return output


@pytest.fixture
def migrations(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    calls: list[Any] = []

    def migrate(root: Path, force: bool = False, prune: bool = False) -> dict[str, Any]:
        calls.append((root, force, prune))
        return {"to": "3.0", "removed": []}

    monkeypatch.setattr(cli, "migrate_payload", migrate)
    return calls


@pytest.mark.parametrize("target", ["2.0", "3.1", "", "3"])
def test_migrate_refuses_unsupported_targets_before_touching_the_project(
    migrations: list[Any], printed: list[Any], tmp_path: Path, target: str
) -> None:
    args = argparse.Namespace(to=target, project_root=str(tmp_path), force=True)
    with pytest.raises(AgenticError) as caught:
        cli.command_migrate(args)
    assert str(caught.value) == "only migration target 3.0 is supported"
    assert (migrations, printed) == ([], [])


def test_migrate_forwards_force_and_prune(
    migrations: list[Any], printed: list[Any], tmp_path: Path
) -> None:
    base = {"to": "3.0", "project_root": str(tmp_path)}
    assert cli.command_migrate(argparse.Namespace(**base, force=True, prune=True)) == 0
    assert cli.command_migrate(argparse.Namespace(**base, force=False)) == 0
    assert migrations == [(tmp_path, True, True), (tmp_path, False, False)]
    assert printed == [{"to": "3.0", "removed": []}] * 2


@pytest.mark.parametrize(("status", "code"), [("PASS", 0), ("FAIL", 1)])
def test_hygiene_exit_code_follows_the_report(
    monkeypatch: pytest.MonkeyPatch, printed: list[Any], tmp_path: Path, status: str, code: int
) -> None:
    calls: list[Any] = []
    report = {"status": status, "unauthorized_fallbacks": []}
    monkeypatch.setattr(cli, "hygiene", lambda root, base: calls.append((root, base)) or report)
    args = argparse.Namespace(project_root=str(tmp_path), base_ref="origin/main")
    assert cli.command_hygiene(args) == code
    assert calls == [(tmp_path, "origin/main")]
    assert printed == [report]
