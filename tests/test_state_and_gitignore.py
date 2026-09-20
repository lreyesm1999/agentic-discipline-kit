"""Control state location and the managed .gitignore block.

`state_dir` is where the control database lives and must never follow a symlink out
of the project, and `_update_gitignore` adds the block that keeps generated outputs
out of commits exactly once. Existing tests saw both only through adoption and init,
so the refusal, the idempotence marker or the written block could change unnoticed.
Each case pins the exact path, file content or action.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from agentic_discipline.bootstrap import _update_gitignore
from agentic_discipline.control.contracts import ControlError
from agentic_discipline.control.plane import state_dir

BLOCK = (
    "\n# Agentic Discipline managed outputs\n"
    "artifacts/\n"
    ".agent-memory/\n"
    ".agentic/verification/artifacts/\n"
    ".agentic/export/\n"
    ".agentic/control/\n"
)
posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX symlinks")


# --- state_dir ------------------------------------------------------------------------------


def test_state_lives_under_agentic_control_whether_or_not_it_exists(tmp_path: Path) -> None:
    assert state_dir(tmp_path) == tmp_path / ".agentic" / "control"
    (tmp_path / ".agentic" / "control").mkdir(parents=True)
    assert state_dir(tmp_path) == tmp_path / ".agentic" / "control"


@posix_only
@pytest.mark.parametrize("linked", [".agentic", ".agentic/control"])
def test_state_directories_reached_through_a_symlink_are_refused(
    tmp_path: Path, linked: str
) -> None:
    root = tmp_path / "project"
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / linked).parent.mkdir(parents=True, exist_ok=True)
    (root / linked).symlink_to(outside, target_is_directory=True)
    with pytest.raises(ControlError) as caught:
        state_dir(root)
    assert (caught.value.code, str(caught.value)) == (
        "INVALID_PATH",
        "Control state cannot follow symlinks",
    )


# --- _update_gitignore ----------------------------------------------------------------------


def test_the_block_is_appended_after_existing_rules(tmp_path: Path) -> None:
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("node_modules/\n\n\n", encoding="utf-8")
    actions: list[str] = []

    _update_gitignore(tmp_path, actions, dry_run=False)

    assert gitignore.read_text(encoding="utf-8") == "node_modules/" + BLOCK
    assert actions == [f"UPDATE {gitignore}"]


def test_a_missing_gitignore_is_created_with_the_block(tmp_path: Path) -> None:
    actions: list[str] = []
    _update_gitignore(tmp_path, actions, dry_run=False)
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == BLOCK
    assert actions == [f"UPDATE {tmp_path / '.gitignore'}"]


def test_an_already_configured_gitignore_is_left_alone(tmp_path: Path) -> None:
    gitignore = tmp_path / ".gitignore"
    content = "dist/\n# Agentic Discipline managed outputs\ncustom/\n"
    gitignore.write_text(content, encoding="utf-8")
    actions: list[str] = []

    _update_gitignore(tmp_path, actions, dry_run=False)

    assert gitignore.read_text(encoding="utf-8") == content
    assert actions == [f"SKIP {gitignore} (already configured)"]


def test_dry_run_reports_the_update_without_writing(tmp_path: Path) -> None:
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("dist/\n", encoding="utf-8")
    actions: list[str] = []

    _update_gitignore(tmp_path, actions, dry_run=True)

    assert gitignore.read_text(encoding="utf-8") == "dist/\n"
    assert actions == [f"UPDATE {gitignore}"]
    _update_gitignore(tmp_path / "absent", actions, dry_run=True)
    assert not (tmp_path / "absent").exists()
