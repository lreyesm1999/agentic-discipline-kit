"""Detection looks four directories deep unless told otherwise.

`scan` relies on the default depth, so a project nested four levels down is found
and one nested five levels down is not. A project at the repository root reports its
root as `.`.
"""

from __future__ import annotations

from pathlib import Path

from agentic_discipline.bootstrap import find_contract_root
from agentic_discipline.profiles import detect_projects, load_profiles


def _python_project(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")


def test_the_default_depth_reaches_four_levels_and_no_further(tmp_path: Path) -> None:
    profiles = load_profiles(find_contract_root())
    _python_project(tmp_path / "a" / "b" / "c" / "d")
    _python_project(tmp_path / "e" / "f" / "g" / "h" / "i")

    found = detect_projects(tmp_path, profiles)

    assert [d.root.relative_to(tmp_path.resolve()).as_posix() for d in found] == ["a/b/c/d"]


def test_a_project_at_the_root_reports_its_root_as_a_dot(tmp_path: Path) -> None:
    profiles = load_profiles(find_contract_root())
    _python_project(tmp_path)

    (found,) = detect_projects(tmp_path, profiles)

    assert found.report(tmp_path.resolve())["root"] == "."
