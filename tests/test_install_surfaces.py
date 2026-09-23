"""Cover the human-facing install path: rendered output, listing, migration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from agentic_discipline import cli
from agentic_discipline.bootstrap import find_contract_root
from agentic_discipline.common import AgenticError
from agentic_discipline.migration import LEGACY_PATHS, migrate_payload
from agentic_discipline.skills import (
    load_constitution,
    load_discipline,
    load_disciplines,
    render_frontmatter,
)


def _init_namespace(target: Path, **overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "target": str(target),
        "profile": [],
        "profile_file": [],
        "force": False,
        "max_depth": 4,
        "adapter": [],
        "dry_run": False,
        "json": False,
        "rules_only": False,
        "no_adopt": False,
        "adopt": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_init_prints_a_readable_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "package.json").write_text('{"scripts":{"test":"vitest"}}', encoding="utf-8")

    assert cli.command_init(_init_namespace(project)) == 0

    out = capsys.readouterr().out
    assert "Detected stack   TypeScript / JavaScript" in out
    assert "Disciplines      12 installed" in out
    assert "AGENTS.md, agentic.config.json" in out
    # A relaxed gate is named with its reason, not hidden.
    assert "typescript/lint" in out
    # One command leaves the project able to run the workflow, and the report closes on that
    # rather than on another command to type.
    assert "Control plane    the repository was adopted and indexed" in out
    assert "Status: READY FOR AGENTIC EXECUTION" in out
    assert "Next:  ask for the work you want done." in out
    assert not out.lstrip().startswith("{")


def test_init_dry_run_says_so_and_json_stays_machine_readable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text('[project]\nname="x"\n', encoding="utf-8")

    assert cli.command_init(_init_namespace(project, dry_run=True)) == 0
    assert "DRY RUN" in capsys.readouterr().out

    assert cli.command_init(_init_namespace(project, json=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "PASS"
    assert payload["disciplines"]


def test_adapters_sync_reports_changes_then_reports_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    namespace = argparse.Namespace(
        project_root=str(project), adapter=["cursor"], dry_run=False, json=False
    )

    assert cli.command_adapters_sync(namespace) == 0
    first = capsys.readouterr().out
    assert "Cursor" in first
    assert ".cursor/rules/agentic-coding.mdc" in first

    assert cli.command_adapters_sync(namespace) == 0
    assert "Everything already synchronized." in capsys.readouterr().out


def test_adapters_list_reports_targets_and_detection(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = tmp_path / "project"
    (project / ".claude").mkdir(parents=True)

    assert cli.command_adapters_list(argparse.Namespace(project_root=str(project))) == 0

    payload = json.loads(capsys.readouterr().out)
    identifiers = {item["id"] for item in payload["adapters"]}
    assert {"claude", "cursor", "copilot", "generic", "chatgpt"} <= identifiers
    assert payload["aliases"]["codex"] == "generic"
    assert set(payload["detected"]) == {"generic", "claude"}


def test_migrate_moves_and_prunes_the_legacy_root_payload(tmp_path: Path) -> None:
    project = tmp_path / "legacy"
    project.mkdir()
    (project / "package.json").write_text("{}", encoding="utf-8")
    kit = find_contract_root()
    for relative in LEGACY_PATHS:
        source = kit / relative
        target = project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            target.mkdir(exist_ok=True)
            (target / "leftover.md").write_text("stale\n", encoding="utf-8")
        else:
            target.write_text("stale\n", encoding="utf-8")

    report = migrate_payload(project)
    assert report["legacy_remaining"]
    assert any("migrate --prune" in action for action in report["manual_actions"])

    pruned = migrate_payload(project, prune=True)
    assert set(pruned["removed"]) == set(LEGACY_PATHS)
    assert pruned["legacy_remaining"] == []
    for relative in LEGACY_PATHS:
        assert not (project / relative).exists()
    # The payload survives the prune under its new home.
    assert (project / ".agentic" / "MASTER_PROMPT.md").is_file()
    assert (project / ".agentic" / "policies").is_dir()


def test_migrate_keeps_a_config_directory_the_project_still_uses(tmp_path: Path) -> None:
    project = tmp_path / "legacy"
    (project / "config").mkdir(parents=True)
    (project / "config" / "risk-weights.json").write_text("{}", encoding="utf-8")
    (project / "config" / "app.yaml").write_text("owned by the project\n", encoding="utf-8")

    migrate_payload(project, prune=True)

    assert not (project / "config" / "risk-weights.json").exists()
    assert (project / "config" / "app.yaml").is_file()


def test_discipline_loading_rejects_incomplete_sources(tmp_path: Path) -> None:
    with pytest.raises(AgenticError, match="canonical disciplines not found"):
        load_disciplines(tmp_path)

    empty = tmp_path / "disciplines"
    empty.mkdir()
    with pytest.raises(AgenticError, match="no disciplines found"):
        load_disciplines(tmp_path)

    incomplete = empty / "01-broken"
    incomplete.mkdir()
    (incomplete / "SKILL.md").write_text(
        render_frontmatter({"id": "broken"}) + "\nbody\n", encoding="utf-8"
    )
    with pytest.raises(AgenticError, match="missing frontmatter keys"):
        load_disciplines(tmp_path)

    with pytest.raises(AgenticError, match="canonical constitution not found"):
        load_constitution(tmp_path)


def test_discipline_defaults_apply_when_optional_metadata_is_absent(tmp_path: Path) -> None:
    path = tmp_path / "SKILL.md"
    path.write_text(
        render_frontmatter({"id": "demo", "name": "agentic-demo", "description": "Use when demo."})
        + "\nbody\n",
        encoding="utf-8",
    )

    discipline = load_discipline(path)

    assert discipline.title == "Demo"
    assert discipline.globs == ("**",)
    assert discipline.always is False
    assert discipline.phase == "implementation"
    assert discipline.glob_list == "**"


def test_duplicate_discipline_ids_are_rejected(tmp_path: Path) -> None:
    disciplines = tmp_path / "disciplines"
    for name in ("01-a", "02-b"):
        folder = disciplines / name
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text(
            render_frontmatter({"id": "same", "name": "agentic-same", "description": "Use it."})
            + "\nbody\n",
            encoding="utf-8",
        )

    with pytest.raises(AgenticError, match="duplicate discipline ids"):
        load_disciplines(tmp_path)


def test_relative_falls_back_to_the_original_path(tmp_path: Path) -> None:
    outside = (tmp_path / "elsewhere" / "file.md").resolve()
    assert cli._relative(str(outside), (tmp_path / "project").resolve()) == str(outside)
