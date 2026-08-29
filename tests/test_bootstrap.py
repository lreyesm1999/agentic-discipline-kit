import json
from pathlib import Path

import pytest

from agentic_discipline.bootstrap import bootstrap_project, initialize_project
from agentic_discipline.common import AgenticError


def test_bootstrap_creates_complete_target(tmp_path: Path) -> None:
    target = tmp_path / "target"
    actions = bootstrap_project(target, "python")
    assert (target / "AGENTS.md").is_file()
    assert (target / "agentic.config.json").is_file()
    assert (target / "config" / "risk-weights.json").is_file()
    assert len(list((target / "skills").glob("*/SKILL.md"))) == 20
    assert any(action.startswith("READY") for action in actions)
    repeated = bootstrap_project(target, "python")
    assert any(action.startswith("SKIP") for action in repeated)

    (target / "AGENTS.md").write_text("old", encoding="utf-8")
    bootstrap_project(target, "python", force=True)
    assert (target / "AGENTS.md").read_text(encoding="utf-8") != "old"


def test_bootstrap_refuses_filesystem_root() -> None:
    root = Path(Path.cwd().anchor)
    with pytest.raises(AgenticError, match="filesystem root"):
        bootstrap_project(root, "python")


def test_bootstrap_refuses_unknown_stack_and_kit_root() -> None:
    with pytest.raises(AgenticError, match="profile not found"):
        bootstrap_project(Path.cwd() / "target", "rust")
    with pytest.raises(AgenticError, match="into itself"):
        bootstrap_project(Path.cwd(), "python")


def test_init_autodetects_multiple_project_ecosystems(tmp_path: Path) -> None:
    target = tmp_path / "mixed-app"
    target.mkdir()
    (target / "package.json").write_text('{"scripts":{"test":"vitest"}}', encoding="utf-8")
    api = target / "api"
    api.mkdir()
    (api / "service.csproj").write_text("<Project />", encoding="utf-8")

    result = initialize_project(target)

    assert result["profiles"] == ["typescript", "dotnet"]
    assert result["detections"][0]["root"] == "."
    assert result["detections"][1]["root"] == "api"
    config = json.loads((target / "agentic.config.json").read_text(encoding="utf-8"))
    assert any(gate["name"].startswith("typescript/") for gate in config["gates"])
    dotnet_gates = [gate for gate in config["gates"] if gate["name"].startswith("dotnet@api/")]
    assert dotnet_gates
    assert all(gate["working_directory"] == "api" for gate in dotnet_gates)


def test_init_uses_generic_profile_when_stack_is_unknown(tmp_path: Path) -> None:
    target = tmp_path / "unknown"
    target.mkdir()
    (target / "main.zig").write_text("pub fn main() void {}", encoding="utf-8")

    result = initialize_project(target)

    assert result["profiles"] == ["generic"]
    config = json.loads((target / "agentic.config.json").read_text(encoding="utf-8"))
    assert config["gates"][0]["command"] == ["git", "diff", "--check"]
