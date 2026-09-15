"""Human `adapters sync` report, line by line.

After compiling disciplines for each agent surface, the command prints what changed.
The existing tests only ran sync and checked actions, so the dry-run banner, the
"already synchronized" message or the relative paths could change unnoticed. Each
case compares the whole printed report.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agentic_discipline.cli import _relative, _render_adapters


def _result(**changes: object) -> dict[str, object]:
    return {
        "dry_run": False,
        "labels": ["Claude Code", "Cursor"],
        "disciplines": ["a", "b", "c"],
        "actions": [],
        **changes,
    }


def test_changed_files_are_listed_with_padded_verbs_and_relative_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path.resolve()
    outside = tmp_path.parent / "elsewhere.md"
    actions = [
        f"WRITE {root / 'AGENTS.md'}",
        f"SKIP {root / '.cursor' / 'rules.mdc'} (unchanged)",
        f"UPDATE {root / '.claude' / 'skills' / 'demo' / 'SKILL.md'} (content changed)",
        f"REMOVE {outside}",
    ]

    _render_adapters(_result(actions=actions), root)

    assert capsys.readouterr().out.splitlines() == [
        "Compiled 3 disciplines for:",
        "  - Claude Code",
        "  - Cursor",
        "",
        "  WRITE  AGENTS.md",
        "  UPDATE .claude/skills/demo/SKILL.md",
        f"  REMOVE {outside}",
    ]


@pytest.mark.parametrize("actions", [[], ["SKIP a (unchanged)", "SKIP b (unchanged)"]])
def test_nothing_to_change_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], actions: list[str]
) -> None:
    _render_adapters(_result(actions=actions, labels=["Generic AGENTS.md"]), tmp_path)
    assert capsys.readouterr().out.splitlines() == [
        "Compiled 3 disciplines for:",
        "  - Generic AGENTS.md",
        "",
        "Everything already synchronized.",
    ]


def test_dry_run_is_announced_first(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _render_adapters(_result(dry_run=True, actions=[f"WRITE {tmp_path / 'x.md'}"]), tmp_path)
    assert capsys.readouterr().out.splitlines() == [
        "DRY RUN - nothing was written.",
        "",
        "Compiled 3 disciplines for:",
        "  - Claude Code",
        "  - Cursor",
        "",
        "  WRITE  x.md",
    ]


def test_relative_paths_fall_back_to_the_original_text(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    assert _relative(str(root / "docs" / "guide.md"), root) == "docs/guide.md"
    assert _relative("relative-outside.md", root / "nested") == "relative-outside.md"
