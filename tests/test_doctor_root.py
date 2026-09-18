"""Which directory `doctor` decides to inspect.

`doctor` reports on the project that encloses the working directory, so it has to
walk upwards and recognise two shapes: an installed project (`AGENTS.md` beside
`.agentic/`) and the kit checkout (`AGENTS.md` beside `disciplines/`). Existing
tests always ran it from the project root, so the walk, the two shapes and the
fallback were never exercised: doctor would silently report on the wrong
directory. Each case runs from somewhere else and pins the directory chosen.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from agentic_discipline.cli import _doctor_root


def _installed(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "AGENTS.md").write_text("# rules\n", encoding="utf-8")
    (root / ".agentic").mkdir()
    return root


def _checkout(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "AGENTS.md").write_text("# rules\n", encoding="utf-8")
    (root / "disciplines").mkdir()
    return root


def test_an_installed_project_is_found_from_a_nested_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _installed(tmp_path / "project")
    nested = root / "src" / "deep"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    assert _doctor_root() == root.resolve()


def test_the_kit_checkout_is_recognised_by_its_disciplines_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _checkout(tmp_path / "kit")
    nested = root / "tests"
    nested.mkdir()
    monkeypatch.chdir(nested)

    assert _doctor_root() == root.resolve()


@pytest.mark.parametrize(
    ("description", "build"),
    [
        (
            "agents file alone",
            lambda root: (root / "AGENTS.md").write_text("x\n", encoding="utf-8"),
        ),
        ("agentic directory alone", lambda root: (root / ".agentic").mkdir()),
        ("disciplines directory alone", lambda root: (root / "disciplines").mkdir()),
    ],
    ids=["agents-only", "agentic-only", "disciplines-only"],
)
def test_half_a_project_is_not_a_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    description: str,
    build: Callable[[Path], object],
) -> None:
    # Both halves are required; one alone must not be mistaken for a project root.
    root = tmp_path / "partial"
    root.mkdir()
    build(root)
    working = root / "work"
    working.mkdir()
    monkeypatch.chdir(working)

    assert _doctor_root() == working.resolve()


def test_the_nearest_enclosing_project_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outer = _installed(tmp_path / "outer")
    inner = _installed(outer / "packages" / "inner")
    monkeypatch.chdir(inner)

    assert _doctor_root() == inner.resolve()


def test_without_any_project_the_working_directory_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    working = tmp_path / "nothing" / "here"
    working.mkdir(parents=True)
    monkeypatch.chdir(working)

    assert _doctor_root() == working.resolve()
