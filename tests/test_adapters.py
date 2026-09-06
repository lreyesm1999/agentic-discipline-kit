from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentic_discipline.adapters import (
    EMITTERS,
    detect_adapters,
    resolve_adapters,
    sync_adapters,
)
from agentic_discipline.bootstrap import find_contract_root, initialize_project
from agentic_discipline.common import AgenticError
from agentic_discipline.skills import load_disciplines, parse_frontmatter, render_frontmatter

EXPECTED_DISCIPLINES = 11


def _frontmatter(path: Path) -> dict[str, str]:
    metadata, _body = parse_frontmatter(path.read_text(encoding="utf-8"), str(path))
    return metadata


def test_every_discipline_declares_activation_metadata() -> None:
    disciplines = load_disciplines(find_contract_root())
    assert len(disciplines) == EXPECTED_DISCIPLINES
    for discipline in disciplines:
        assert discipline.name.startswith("agentic-")
        # The description is what makes a tool decide to load the skill at all.
        assert len(discipline.description) > 40
        assert discipline.when_to_use, f"{discipline.id} has no trigger condition"
        assert discipline.globs
        # Single-field dialects only get `summary`, so it must carry both halves.
        assert discipline.summary.startswith(discipline.description)
        assert " Use " in discipline.summary
        # "When strengthening" must not become "Use when: when strengthening".
        assert "when: when " not in discipline.summary.lower()


def test_single_field_dialects_keep_the_trigger_in_their_description(tmp_path: Path) -> None:
    """Cursor, Windsurf and Copilot decide from one field; dropping the trigger
    there would cost the selectivity the metadata exists for."""

    project = tmp_path / "project"
    project.mkdir()
    sync_adapters(project, ["claude", "cursor", "windsurf", "copilot"])

    claude = _frontmatter(project / ".claude" / "skills" / "agentic-coding" / "SKILL.md")
    assert claude["when_to_use"] == "When writing or modifying production code."
    assert "Use when:" not in claude["description"]

    for path in (
        project / ".cursor" / "rules" / "agentic-coding.mdc",
        project / ".windsurf" / "rules" / "agentic-coding.md",
        project / ".github" / "instructions" / "agentic-coding.instructions.md",
    ):
        metadata = _frontmatter(path)
        assert "when_to_use" not in metadata
        assert "Use when writing or modifying production code." in metadata["description"]


def test_dialects_are_not_the_same_file(tmp_path: Path) -> None:
    """The previous implementation copied one body to every path."""

    project = tmp_path / "project"
    project.mkdir()
    sync_adapters(project, ["claude", "cursor", "windsurf", "copilot"])
    rendered = {
        "claude": project / ".claude" / "skills" / "agentic-coding" / "SKILL.md",
        "cursor": project / ".cursor" / "rules" / "agentic-coding.mdc",
        "windsurf": project / ".windsurf" / "rules" / "agentic-coding.md",
        "copilot": project / ".github" / "instructions" / "agentic-coding.instructions.md",
    }
    for path in rendered.values():
        assert path.is_file()
    contents = {path.read_text(encoding="utf-8") for path in rendered.values()}
    assert len(contents) == len(rendered)

    assert _frontmatter(rendered["claude"])["name"] == "agentic-coding"
    assert "description" in _frontmatter(rendered["claude"])
    cursor = _frontmatter(rendered["cursor"])
    assert cursor["alwaysApply"] in {"true", "false"}
    assert "globs" in cursor
    assert _frontmatter(rendered["windsurf"])["trigger"] in {"always_on", "glob"}
    assert "applyTo" in _frontmatter(rendered["copilot"])


def test_every_emitter_produces_output(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    for name in EMITTERS:
        result = sync_adapters(project, [name])
        assert result["status"] == "PASS"
        assert any(str(action).startswith(("WRITE", "UPDATE")) for action in result["actions"])


def test_agents_md_keeps_user_content(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    agents = project / "AGENTS.md"
    agents.write_text("# House rules\n\nDeploy on Fridays never.\n", encoding="utf-8")
    sync_adapters(project, ["generic"])
    content = agents.read_text(encoding="utf-8")
    assert "Deploy on Fridays never." in content
    assert "Agentic Discipline" in content

    sync_adapters(project, ["generic"])
    assert agents.read_text(encoding="utf-8").count("agentic-discipline:managed:start") == 1


def test_sync_is_idempotent_and_prunes_stale_files(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    sync_adapters(project, ["cursor"])
    second = sync_adapters(project, ["cursor"])
    assert all(str(action).startswith("SKIP") for action in second["actions"])

    stale = project / ".cursor" / "rules" / "agentic-removed.mdc"
    stale.write_text("---\ndescription: gone\n---\n", encoding="utf-8")
    third = sync_adapters(project, ["cursor"])
    assert any("REMOVE" in str(action) for action in third["actions"])
    assert not stale.exists()


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    result = sync_adapters(project, ["claude"], dry_run=True)
    assert result["dry_run"] is True
    assert result["actions"]
    assert not (project / ".claude").exists()
    assert not (project / ".agentic").exists()


def test_aliases_resolve_and_deduplicate() -> None:
    assert resolve_adapters(["codex", "generic", "zed"]) == ["generic"]
    with pytest.raises(ValueError, match="unknown adapters"):
        resolve_adapters(["notatool"])


def test_detection_reports_only_present_tools(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / ".cursor").mkdir(parents=True)
    assert set(detect_adapters(project)) == {"generic", "cursor"}


def test_chatgpt_export_is_a_single_pasteable_bundle(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    sync_adapters(project, ["chatgpt"])
    bundle = project / ".agentic" / "export" / "chatgpt" / "agentic-discipline.md"
    text = bundle.read_text(encoding="utf-8")
    for discipline in load_disciplines(find_contract_root()):
        assert discipline.title in text


def test_init_installs_into_agentic_and_keeps_the_root_clean(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "package.json").write_text('{"scripts":{"test":"vitest"}}', encoding="utf-8")

    initialize_project(project)

    entries = {path.name for path in project.iterdir()}
    assert entries == {".agentic", ".gitignore", "AGENTS.md", "agentic.config.json", "package.json"}
    assert (project / ".agentic" / "MASTER_PROMPT.md").is_file()
    assert (project / ".agentic" / "policies").is_dir()
    # Phase directories are created on demand, not scattered up front.
    assert not (project / "specs").exists()
    assert not (project / "artifacts").exists()


def test_init_relaxes_gates_the_project_cannot_run(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "package.json").write_text('{"scripts":{"test":"vitest"}}', encoding="utf-8")

    result = initialize_project(project)

    config = json.loads((project / "agentic.config.json").read_text(encoding="utf-8"))
    gates = {gate["name"]: gate for gate in config["gates"]}
    lint = gates["typescript/lint"]
    assert lint["required"] is False
    assert "no 'lint' script" in lint["note"]
    # A script the project really defines is left exactly as the profile declared.
    assert gates["typescript/unit-tests"]["required"] is True
    assert "note" not in gates["typescript/unit-tests"]
    assert [item["name"] for item in result["relaxed_gates"]]


def test_init_dry_run_reports_without_touching_the_project(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "package.json").write_text("{}", encoding="utf-8")

    result = initialize_project(project, dry_run=True)

    assert result["dry_run"] is True
    assert result["actions"]
    assert {path.name for path in project.iterdir()} == {"package.json"}


def test_frontmatter_round_trip() -> None:
    fields = {"name": "agentic-demo", "description": "Use when: something happens."}
    metadata, body = parse_frontmatter(render_frontmatter(fields) + "\nbody\n", "demo")
    assert metadata == fields
    assert body.strip() == "body"


def test_frontmatter_rejects_malformed_blocks() -> None:
    with pytest.raises(AgenticError, match="unterminated"):
        parse_frontmatter("---\nname: x\n", "demo")
    with pytest.raises(AgenticError, match="invalid frontmatter"):
        parse_frontmatter("---\nbroken line\n---\n", "demo")
    assert parse_frontmatter("# no frontmatter\n", "demo") == ({}, "# no frontmatter\n")
