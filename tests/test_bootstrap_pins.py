"""Pins for bootstrap.py and cli.py mutation survivors."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentic_discipline import bootstrap, cli


def test_initialize_project_preserves_rules_only_unless_adopt_requested(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    config_dir = root / ".agentic"
    config_dir.mkdir(parents=True)
    (config_dir / "config.json").write_text(
        json.dumps({"control": {"mode": "rules-only"}}), encoding="utf-8"
    )

    # Calling with adopt=True explicitly changes the recorded mode to managed and adopts
    result = bootstrap.initialize_project(root, adopt=True)
    assert result["control"]["status"] == "ADOPTED"
    assert "control mode managed" in " ".join(result["actions"])


def test_initialize_project_rules_only_on_fresh_project_skips_control(tmp_path: Path) -> None:
    root = tmp_path / "fresh"
    root.mkdir()
    result = bootstrap.initialize_project(root, rules_only=True)
    assert result["control"]["status"] == "SKIPPED"
    assert result["control"]["detail"] == "installed rules-only, so the control plane was not initialised"


def test_initialize_project_rules_only_on_adopted_project_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "adopted"
    root.mkdir()
    bootstrap.initialize_project(root, adopt=True)

    result = bootstrap.initialize_project(root, rules_only=True)
    assert result["control"]["status"] == "REFUSED"
    assert result["control"]["detail"].startswith("this project is already adopted, so --rules-only was not recorded")


def test_command_init_honors_no_adopt_flag(tmp_path: Path) -> None:
    target = tmp_path / "noadopt"
    args = argparse.Namespace(
        target=str(target),
        profile=[],
        profile_file=[],
        force=False,
        max_depth=4,
        adapter=[],
        dry_run=False,
        adopt=False,
        no_adopt=True,
        rules_only=False,
        json=True,
    )
    code = cli.command_init(args)
    # Not adopted means readiness is PARTIAL, so init returns 1 to signal unadopted state
    assert code == 1
    assert not (target / ".agentic" / "control" / "state.db").exists()


def test_command_repair_returns_one_on_failure(tmp_path: Path) -> None:
    root = tmp_path / "broken"
    root.mkdir()
    bootstrap.initialize_project(root, adopt=True)
    (root / ".agentic" / "control" / "state.db").write_bytes(b"corrupt")

    args = argparse.Namespace(
        project_root=str(root),
        dry_run=False,
        fast=False,
        json=True,
    )
    # Ensure current directory is root so _doctor_root finds it
    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(root)
        code = cli.command_repair(args)
        assert code == 1
    finally:
        os.chdir(old_cwd)
