"""Generated project documents pinned byte for byte.

Adopting projects and the Claude Code marketplace read these files directly, so
their exact keys, values and layout are a contract. Earlier tests only checked
that the files existed or read one field, which left most of their content free
to change unnoticed.
"""

from __future__ import annotations

import json
from pathlib import Path

from agentic_discipline import adapters
from agentic_discipline.adapters import COMMANDS, _rules, sync_adapters
from agentic_discipline.bootstrap import initialize_project

EXPECTED_CONFIG = {
    "schema_version": "3",
    "adk": {"risk_default": "STANDARD", "unknown_blocks_release": True},
    "agents": {"mode": "auto", "adapters": ["generic"]},
    "verification": {
        "root": ".agentic/verification",
        "generated_root": ".agentic/verification/generated",
        "require_sensitivity_for_generated": True,
        "protect_validated_verifiers": True,
        "default_timeout_seconds": 120,
    },
    "evidence": {"root": "artifacts/agentic", "hash": "sha256"},
}
EXPECTED_REGISTRY = {"schema_version": "1", "verifiers": []}


def _json_text(document: object) -> str:
    return json.dumps(document, indent=2) + "\n"


def test_initialized_project_writes_the_exact_payload_config_and_registry(tmp_path: Path) -> None:
    target = tmp_path / "target"
    initialize_project(target)

    verification = target / ".agentic" / "verification"
    assert (target / ".agentic" / "config.json").read_text(encoding="utf-8") == _json_text(
        EXPECTED_CONFIG
    )
    assert (verification / "registry.json").read_text(encoding="utf-8") == _json_text(
        EXPECTED_REGISTRY
    )
    assert (verification / "generated").is_dir()
    assert (verification / "artifacts").is_dir()


def test_force_restores_payload_files_config_and_registry(tmp_path: Path) -> None:
    target = tmp_path / "target"
    initialize_project(target)
    config = target / ".agentic" / "config.json"
    registry = target / ".agentic" / "verification" / "registry.json"
    risk_weights = target / ".agentic" / "config" / "risk-weights.json"
    for path in (config, registry, risk_weights):
        path.write_text("{}", encoding="utf-8")

    initialize_project(target)
    assert [path.read_text(encoding="utf-8") for path in (config, registry, risk_weights)] == [
        "{}"
    ] * 3

    initialize_project(target, force=True)
    assert config.read_text(encoding="utf-8") == _json_text(EXPECTED_CONFIG)
    assert registry.read_text(encoding="utf-8") == _json_text(EXPECTED_REGISTRY)
    assert risk_weights.read_text(encoding="utf-8") != "{}"


def test_claude_plugin_manifest_is_exact(tmp_path: Path) -> None:
    sync_adapters(tmp_path, ["claude-plugin"])

    manifest = tmp_path / ".claude-plugin" / "plugin.json"
    assert manifest.read_text(encoding="utf-8") == _json_text(
        {
            "name": "agentic-discipline",
            "description": (
                "Evidence-backed engineering discipline for AI coding agents: "
                "requirements, acceptance, verification, hardening, and release evidence."
            ),
            "version": adapters.__version__,
            "author": {"name": "Agentic Discipline Kit Contributors"},
            "homepage": "https://github.com/lreyesm1999/agentic-discipline-kit",
            "license": "MIT",
            "keywords": ["quality-gates", "verification", "acceptance-testing", "evidence"],
        }
    )


def test_claude_plugin_commands_list_their_disciplines_in_order(tmp_path: Path) -> None:
    sync_adapters(tmp_path, ["claude-plugin"])
    kit_root = adapters.find_contract_root()
    by_id = {item.id: item for item in adapters.load_disciplines(kit_root)}
    rules = _rules(adapters.load_constitution(kit_root))

    assert COMMANDS, "the plugin must ship slash commands"
    for name, summary, argument_hint, discipline_ids in COMMANDS:
        referenced = [by_id[item] for item in discipline_ids]
        assert referenced, f"/{name} must reference at least one discipline"
        steps = "\n".join(
            f"{number}. Apply **{item.title}** (`{item.name}`): {item.description}"
            for number, item in enumerate(referenced, start=1)
        )
        expected = (
            adapters.render_frontmatter({"description": summary, "argument-hint": argument_hint})
            + "\n"
            + f"# /{name}\n\n{summary}\n\n## Steps\n\n{steps}\n\n"
            + f"## Stop conditions\n\n{rules}\n\n"
            + "Report `UNKNOWN` or `BLOCKED` rather than presenting an unproven claim as `PASS`.\n"
        )
        path = tmp_path / "commands" / f"{name}.md"
        assert path.read_text(encoding="utf-8") == expected, name
