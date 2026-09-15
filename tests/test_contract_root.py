"""Locating the packaged contract bundle, candidate by candidate.

Every install surface reads disciplines and profiles from the root
`find_contract_root` returns, whether the kit runs from a checkout, a configured
path, a frozen binary or an installed wheel. Existing tests only ran inside the
checkout, so the candidate order, the completeness rule or the final error could
change unnoticed. Each case builds bundles in a temporary tree and pins the root found.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from agentic_discipline import bootstrap
from agentic_discipline.bootstrap import find_contract_root
from agentic_discipline.common import AgenticError


def _bundle(root: Path, *, missing: str | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    if missing != "agents":
        (root / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    if missing != "disciplines":
        (root / "disciplines").mkdir()
    if missing != "profile":
        profile = root / "config" / "profiles" / "generic.json"
        profile.parent.mkdir(parents=True)
        profile.write_text("{}", encoding="utf-8")
    return root


@pytest.fixture
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Path]:
    """Point every candidate source at an empty temporary tree."""
    paths = {
        "module": tmp_path / "site" / "agentic_discipline" / "bootstrap.py",
        "cwd": tmp_path / "work" / "deep",
        "data": tmp_path / "data",
        "frozen": tmp_path / "frozen",
    }
    paths["cwd"].mkdir(parents=True)
    monkeypatch.setattr(bootstrap, "__file__", str(paths["module"]))
    monkeypatch.chdir(paths["cwd"])
    monkeypatch.delenv("AGENTIC_DISCIPLINE_CONTRACT_ROOT", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(
        bootstrap.sysconfig,
        "get_path",
        lambda name: str(paths["data"] if name == "data" else tmp_path / "other"),
    )
    return paths


def test_without_any_bundle_the_contracts_are_not_found(isolated: dict[str, Path]) -> None:
    _bundle(isolated["cwd"] / "nested")
    with pytest.raises(AgenticError) as caught:
        find_contract_root()
    assert str(caught.value) == "packaged Agentic Discipline contracts were not found"


def test_a_configured_root_wins_and_expands_the_home_directory(
    isolated: dict[str, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    configured = _bundle(home / "contracts")
    _bundle(isolated["cwd"])
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("AGENTIC_DISCIPLINE_CONTRACT_ROOT", "~/contracts")
    assert find_contract_root() == configured.resolve()


@pytest.mark.parametrize("missing", ["agents", "disciplines", "profile"])
def test_incomplete_bundles_are_skipped(
    isolated: dict[str, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path, missing: str
) -> None:
    partial = _bundle(tmp_path / "partial", missing=missing)
    monkeypatch.setenv("AGENTIC_DISCIPLINE_CONTRACT_ROOT", str(partial))
    complete = _bundle(isolated["cwd"])
    assert find_contract_root() == complete.resolve()


def test_bundle_parts_must_have_the_right_kind(
    isolated: dict[str, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    wrong = tmp_path / "wrong"
    (wrong / "AGENTS.md").mkdir(parents=True)
    (wrong / "disciplines").write_text("", encoding="utf-8")
    (wrong / "config" / "profiles" / "generic.json").mkdir(parents=True)
    monkeypatch.setenv("AGENTIC_DISCIPLINE_CONTRACT_ROOT", str(wrong))
    with pytest.raises(AgenticError):
        find_contract_root()


def test_the_package_location_is_searched_before_the_working_directory(
    isolated: dict[str, Path],
) -> None:
    package_root = _bundle(isolated["module"].parent.parent)
    _bundle(isolated["cwd"])
    assert find_contract_root() == package_root.resolve()


def test_working_directory_ancestors_are_searched_before_the_directory_itself(
    isolated: dict[str, Path],
) -> None:
    ancestor = _bundle(isolated["cwd"].parent)
    _bundle(isolated["cwd"])
    assert find_contract_root() == ancestor.resolve()


def test_frozen_bundles_come_before_installed_data(
    isolated: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    frozen = _bundle(isolated["frozen"])
    installed = _bundle(isolated["data"] / "share" / "agentic-discipline")
    monkeypatch.setattr(sys, "_MEIPASS", str(frozen), raising=False)
    assert find_contract_root() == frozen.resolve()
    monkeypatch.delattr(sys, "_MEIPASS")
    assert find_contract_root() == installed.resolve()
