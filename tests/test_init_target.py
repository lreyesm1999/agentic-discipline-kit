"""Initializing into a directory that does not exist yet.

A user runs `agentic-discipline init clients/acme/new-service` before creating any of
those directories. Every existing test initialized a directory whose parent already
existed, so creating the missing parents was never exercised and could stop working
unnoticed: init would then fail on exactly the first command a new user types.
"""

from __future__ import annotations

from pathlib import Path

from agentic_discipline.bootstrap import initialize_project


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
