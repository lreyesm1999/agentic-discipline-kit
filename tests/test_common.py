from __future__ import annotations

from types import SimpleNamespace

import pytest

from agentic_discipline import common
from agentic_discipline.common import AgenticError


def test_run_git_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        common.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="ok\n", stderr=""),
    )
    assert common.run_git(["status"]) == "ok\n"


def test_run_git_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        common.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout="", stderr="boom"),
    )
    with pytest.raises(AgenticError, match="boom"):
        common.run_git(["status"])


def test_changed_files(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(common, "run_git", lambda _args, cwd=None: "a.py\n\nb.py\n")
    assert common.changed_files("main") == ["a.py", "b.py"]
