"""Where each dialect writes, and what its frontmatter says.

Existing tests assert that an emitter produced *something* and that four dialects
do not share one body, so the directory a tool reads, the file extension it expects
and the frontmatter keys it parses were all free to change unnoticed. A tool whose
rules move to another path silently stops applying them. Each case pins the exact
set of files one adapter writes, and the exact frontmatter each dialect carries.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline.adapters import COMMANDS, EMITTERS, sync_adapters
from agentic_discipline.bootstrap import find_contract_root
from agentic_discipline.skills import load_disciplines, parse_frontmatter


def _disciplines() -> list[Any]:
    return load_disciplines(find_contract_root())


def _frontmatter(path: Path) -> dict[str, str]:
    metadata, _body = parse_frontmatter(path.read_text(encoding="utf-8"), str(path))
    return metadata


def _canonical_paths() -> set[str]:
    paths = {".agentic/constitution/CORE.md"}
    paths.update(f".agentic/skills/{item.slug}/SKILL.md" for item in _disciplines())
    return paths


def _per_discipline(directory: str, suffix: str, nested: bool) -> set[str]:
    stems = [f"agentic-{item.id}" for item in _disciplines()]
    if nested:
        return {f"{directory}/{stem}/SKILL.md" for stem in stems}
    return {f"{directory}/{stem}{suffix}" for stem in stems}


def _expected(adapter: str) -> set[str]:
    if adapter == "generic":
        return {"AGENTS.md"}
    if adapter == "gemini":
        return {"GEMINI.md"}
    if adapter == "chatgpt":
        return {".agentic/export/chatgpt/agentic-discipline.md"}
    if adapter == "claude":
        return _per_discipline(".claude/skills", "", nested=True)
    if adapter == "antigravity":
        return _per_discipline(".agents/skills", "", nested=True)
    if adapter == "cursor":
        return _per_discipline(".cursor/rules", ".mdc", nested=False)
    if adapter == "windsurf":
        return _per_discipline(".windsurf/rules", ".md", nested=False)
    if adapter == "copilot":
        return _per_discipline(".github/instructions", ".instructions.md", nested=False) | {
            ".github/copilot-instructions.md"
        }
    if adapter == "claude-plugin":
        return (
            {".claude-plugin/plugin.json"}
            | _per_discipline("skills", "", nested=True)
            | {f"commands/{name}.md" for name, _, _, _ in COMMANDS}
        )
    raise AssertionError(f"no expected layout recorded for {adapter}")


def _written(project: Path) -> set[str]:
    return {path.relative_to(project).as_posix() for path in project.rglob("*") if path.is_file()}


@pytest.mark.parametrize("adapter", sorted(EMITTERS), ids=sorted(EMITTERS))
def test_each_adapter_writes_exactly_its_own_layout(tmp_path: Path, adapter: str) -> None:
    project = tmp_path / adapter
    project.mkdir()

    sync_adapters(project, [adapter])

    expected = _expected(adapter)
    # Packaging targets build a distributable, so they never receive the payload.
    if adapter != "claude-plugin":
        expected |= _canonical_paths()
    assert _written(project) == expected


def test_the_canonical_payload_is_shared_by_every_project_surface(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()

    sync_adapters(project, ["generic", "claude"])

    assert _canonical_paths() <= _written(project)


@pytest.mark.parametrize(
    ("adapter", "path_template", "keys"),
    [
        ("claude", ".claude/skills/agentic-{id}/SKILL.md", ("name", "description")),
        ("cursor", ".cursor/rules/agentic-{id}.mdc", ("description", "globs", "alwaysApply")),
        ("windsurf", ".windsurf/rules/agentic-{id}.md", ("trigger", "description", "globs")),
        (
            "copilot",
            ".github/instructions/agentic-{id}.instructions.md",
            ("description", "applyTo"),
        ),
    ],
    ids=["claude", "cursor", "windsurf", "copilot"],
)
def test_each_dialect_carries_the_frontmatter_it_reads(
    tmp_path: Path, adapter: str, path_template: str, keys: tuple[str, ...]
) -> None:
    project = tmp_path / adapter
    project.mkdir()
    sync_adapters(project, [adapter])
    discipline = _disciplines()[0]
    metadata = _frontmatter(project / path_template.format(id=discipline.id))

    assert set(metadata) >= set(keys)
    if adapter == "cursor":
        assert metadata["globs"] == discipline.glob_list
        assert metadata["alwaysApply"] == ("true" if discipline.always else "false")
        assert metadata["description"] == discipline.summary
    if adapter == "windsurf":
        assert metadata["globs"] == discipline.glob_list
        assert metadata["trigger"] == ("always_on" if discipline.always else "glob")
    if adapter == "copilot":
        assert metadata["applyTo"] == discipline.glob_list
    if adapter == "claude":
        assert metadata["name"] == discipline.name
        assert metadata["description"] == discipline.description


def test_the_plugin_manifest_names_the_installable_plugin(tmp_path: Path) -> None:
    project = tmp_path / "plugin"
    project.mkdir()

    sync_adapters(project, ["claude-plugin"])

    manifest = json.loads((project / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "agentic-discipline"
    assert manifest["license"] == "MIT"
    assert set(manifest) == {
        "name",
        "description",
        "version",
        "author",
        "homepage",
        "license",
        "keywords",
    }
