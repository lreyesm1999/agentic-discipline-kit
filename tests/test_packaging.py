"""Guard the distribution surfaces that fail silently when they drift.

A discipline missing from ``data-files`` still installs; it only breaks later,
at runtime, with "packaged contracts were not found". A stale plugin copy still
installs too, and simply teaches an older discipline. Both are cheap to assert.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from agentic_discipline import __version__
from agentic_discipline.adapters import sync_adapters

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "packaging" / "claude-plugin"

# These assert about the repository layout itself, so they are meaningless in a
# partial copy. Mutmut runs the suite from a `mutants/` tree holding only the
# mutated sources and the tests, where `packaging/` does not exist.
pytestmark = pytest.mark.skipif(
    not (ROOT / "packaging" / "agentic-discipline.spec").is_file(),
    reason="repository layout unavailable in a partial checkout",
)


def _data_files() -> dict[str, list[str]]:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return pyproject["tool"]["setuptools"]["data-files"]


def _packaged_sources() -> set[str]:
    packaged: set[str] = set()
    for patterns in _data_files().values():
        for pattern in patterns:
            packaged.update(match.as_posix() for match in ROOT.glob(pattern))
            packaged.add((ROOT / pattern).as_posix())
    return packaged


def test_every_discipline_and_playbook_is_packaged() -> None:
    packaged = _packaged_sources()
    missing = [
        path.relative_to(ROOT).as_posix()
        for pattern in ("disciplines/*/SKILL.md", "skills/*/SKILL.md")
        for path in sorted(ROOT.glob(pattern))
        if path.as_posix() not in packaged
    ]
    assert not missing, f"pyproject data-files does not ship: {missing}"


def test_profiles_and_examples_are_packaged() -> None:
    packaged = _packaged_sources()
    for pattern in ("config/profiles/*.json", "config/examples/*.json"):
        for path in sorted(ROOT.glob(pattern)):
            assert path.as_posix() in packaged, f"not packaged: {path}"


def test_standalone_spec_bundles_the_canonical_source() -> None:
    spec = (ROOT / "packaging" / "agentic-discipline.spec").read_text(encoding="utf-8")
    for required in ("disciplines", "agentic", "config/profiles"):
        assert f'"{required}"' in spec, f"standalone build omits {required}"


def test_published_plugin_matches_the_canonical_disciplines(tmp_path: Path) -> None:
    """`packaging/claude-plugin` is generated; a stale copy must fail the build."""

    if not PLUGIN.is_dir():
        raise AssertionError("packaging/claude-plugin has not been generated")
    result = sync_adapters(PLUGIN, ["claude-plugin"], dry_run=True)
    changed = [str(action) for action in result["actions"] if not str(action).startswith("SKIP")]
    assert not changed, (
        "regenerate with: agentic-discipline adapters sync "
        f"--project-root packaging/claude-plugin --adapter claude-plugin; pending: {changed}"
    )


def test_every_command_declares_a_description_and_argument_hint() -> None:
    from agentic_discipline.adapters import COMMANDS
    from agentic_discipline.skills import parse_frontmatter

    commands = sorted((PLUGIN / "commands").glob("*.md"))
    assert {path.stem for path in commands} == {name for name, _, _, _ in COMMANDS}
    for path in commands:
        metadata, _body = parse_frontmatter(path.read_text(encoding="utf-8"), str(path))
        assert metadata["description"]
        # The hint is what the host shows while the user is still typing.
        assert metadata["argument-hint"].startswith("[")


def test_plugin_skills_carry_the_trigger_in_its_own_field() -> None:
    from agentic_discipline.skills import parse_frontmatter

    skills = sorted((PLUGIN / "skills").glob("*/SKILL.md"))
    assert len(skills) == 12
    for path in skills:
        metadata, _body = parse_frontmatter(path.read_text(encoding="utf-8"), str(path))
        assert metadata["name"] == path.parent.name
        assert metadata["description"]
        assert metadata["when_to_use"]


def test_execute_command_resolves_to_the_shipped_orchestrator() -> None:
    from agentic_discipline.adapters import COMMANDS
    from agentic_discipline.skills import load_disciplines

    by_id = {item.id: item for item in load_disciplines(ROOT)}
    execute = next(command for command in COMMANDS if command[0] == "execute")
    assert execute[3] == ("autonomous-project-execution",)
    command = (PLUGIN / "commands" / "execute.md").read_text(encoding="utf-8")
    for identifier in execute[3]:
        discipline = by_id[identifier]
        assert discipline.name in command
        assert (PLUGIN / "skills" / discipline.name / "SKILL.md").is_file()


def test_documented_plugin_install_names_its_marketplace() -> None:
    """`/plugin install <plugin>` without `@<marketplace>` does not resolve."""

    marketplace = json.loads(
        (ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
    )
    qualified = f"/plugin install {marketplace['plugins'][0]['name']}@{marketplace['name']}"
    for document in (ROOT / "README.md", ROOT / "docs" / "install.md"):
        text = document.read_text(encoding="utf-8")
        if "/plugin install" not in text:
            continue
        assert qualified in text, f"{document.name} must document: {qualified}"


def test_marketplace_declares_the_fields_the_loader_requires() -> None:
    marketplace = json.loads(
        (ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
    )
    assert marketplace["name"]
    assert marketplace["owner"]["name"]
    for entry in marketplace["plugins"]:
        assert entry["name"]
        assert entry["source"]

    plugin = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert plugin["name"] == marketplace["plugins"][0]["name"]
    # Auto-discovery relies on these conventional directories beside the manifest.
    assert (PLUGIN / "skills").is_dir()
    assert (PLUGIN / "commands").is_dir()


def test_install_surfaces_declare_one_version() -> None:
    plugin = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    marketplace = json.loads(
        (ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
    )
    npm = json.loads((ROOT / "packaging" / "npm" / "package.json").read_text(encoding="utf-8"))

    assert plugin["version"] == __version__
    assert npm["version"] == __version__
    assert marketplace["plugins"][0]["version"] == __version__
    assert marketplace["plugins"][0]["source"] == "./packaging/claude-plugin"
