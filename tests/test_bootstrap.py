from pathlib import Path

import pytest

from agentic_discipline.bootstrap import bootstrap_project
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
    with pytest.raises(AgenticError, match="unsupported stack"):
        bootstrap_project(Path.cwd() / "target", "rust")
    with pytest.raises(AgenticError, match="into itself"):
        bootstrap_project(Path.cwd(), "python")
