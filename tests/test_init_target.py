"""Initializing into a directory that does not exist yet.

A user runs `agentic-discipline init clients/acme/new-service` before creating any of
those directories. Every existing test initialized a directory whose parent already
existed, so creating the missing parents was never exercised and could stop working
unnoticed: init would then fail on exactly the first command a new user types.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agentic_discipline import bootstrap
from agentic_discipline.bootstrap import _prepare_target, find_contract_root, initialize_project
from agentic_discipline.common import AgenticError


def test_init_creates_a_target_whose_parents_do_not_exist_yet(tmp_path: Path) -> None:
    target = tmp_path / "clients" / "acme" / "new-service"
    assert not target.parent.exists()

    result = initialize_project(target, adapters=["generic"])

    assert result["status"] == "PASS"
    assert (target / "agentic.config.json").is_file()
    assert (target / "AGENTS.md").is_file()


def test_a_dry_run_into_a_missing_target_creates_nothing(tmp_path: Path) -> None:
    target = tmp_path / "clients" / "acme" / "new-service"

    result = initialize_project(target, adapters=["generic"], dry_run=True)

    assert result["dry_run"] is True
    assert not (tmp_path / "clients").exists()


def test_init_refuses_a_filesystem_root_with_its_reason() -> None:
    with pytest.raises(AgenticError) as caught:
        _prepare_target(Path(Path.cwd().anchor), find_contract_root())
    assert str(caught.value) == "refusing to bootstrap into a filesystem root"


def test_init_refuses_the_directory_its_own_package_runs_from() -> None:
    # Running from a checkout, the package sits in `src/`; initializing `src/` itself
    # would write the payload beside the running code.
    package_parent = Path(bootstrap.__file__).resolve().parents[1]
    with pytest.raises(AgenticError) as caught:
        _prepare_target(package_parent, find_contract_root(), dry_run=True)
    assert str(caught.value) == "refusing to bootstrap the kit into itself"


def test_a_project_that_contains_the_package_can_still_be_initialized(tmp_path: Path) -> None:
    # Vendoring the package is not the kit running from the target.
    (tmp_path / "src" / "agentic_discipline").mkdir(parents=True)
    assert _prepare_target(tmp_path, find_contract_root(), dry_run=True) == tmp_path.resolve()
