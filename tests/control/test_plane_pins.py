"""Pins for plane.py mutation survivors."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentic_discipline.control import plane
from agentic_discipline.control.contracts import ControlError


def test_state_dir_refuses_symlinks_for_agentic_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []

    def fake_is_symlink(self: Path) -> bool:
        seen.append(self.as_posix())
        return self.as_posix() == (tmp_path / ".agentic").as_posix()

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)
    with pytest.raises(ControlError) as exc_info:
        plane.state_dir(tmp_path)
    assert exc_info.value.code == "INVALID_PATH"
    assert str(exc_info.value) == "Control state cannot follow symlinks"
    assert (tmp_path / ".agentic").as_posix() in seen


def test_state_dir_refuses_symlinks_for_control_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []

    def fake_is_symlink(self: Path) -> bool:
        seen.append(self.as_posix())
        return self.as_posix() == (tmp_path / ".agentic" / "control").as_posix()

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)
    with pytest.raises(ControlError) as exc_info:
        plane.state_dir(tmp_path)
    assert exc_info.value.code == "INVALID_PATH"
    assert str(exc_info.value) == "Control state cannot follow symlinks"
    assert (tmp_path / ".agentic" / "control").as_posix() in seen


def test_state_dir_returns_control_path_when_not_symlink(tmp_path: Path) -> None:
    assert plane.state_dir(tmp_path) == tmp_path / ".agentic" / "control"
