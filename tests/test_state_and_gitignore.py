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
    content = "dist/" + BLOCK + "\n# mine\ncustom/\n"
    gitignore.write_text(content, encoding="utf-8")
    actions: list[str] = []

    _update_gitignore(tmp_path, actions, dry_run=False)

    assert gitignore.read_text(encoding="utf-8") == content
    assert actions == [f"SKIP {gitignore} (already configured)"]


def test_an_older_install_gains_the_rule_its_block_lacks(tmp_path: Path) -> None:
    """A project adopted before 2.0.0 has the marker but not `.agentic/control/`.

    The rule has to land inside the managed block, and nothing else in the file may move:
    what follows the block belongs to the project, not to this command.
    """

    gitignore = tmp_path / ".gitignore"
    gitignore.write_text(
        "dist/\n"
        "\n"
        "# Agentic Discipline managed outputs\n"
        "artifacts/\n"
        ".agent-memory/\n"
        ".agentic/verification/artifacts/\n"
        ".agentic/export/\n"
        "\n"
        "# mine\n"
        "notes/\n",
        encoding="utf-8",
    )
    actions: list[str] = []

    _update_gitignore(tmp_path, actions, dry_run=False)

    assert gitignore.read_text(encoding="utf-8") == (
        "dist/\n"
        "\n"
        "# Agentic Discipline managed outputs\n"
        "artifacts/\n"
        ".agent-memory/\n"
        ".agentic/verification/artifacts/\n"
        ".agentic/export/\n"
        ".agentic/control/\n"
        "\n"
        "# mine\n"
        "notes/\n"
    )
    assert actions == [f"UPDATE {gitignore} (added .agentic/control/)"]


def test_a_block_of_one_rule_gains_the_rest_inside_it_and_nowhere_else(tmp_path: Path) -> None:
    """The block ends at its first blank line, however few lines it holds.

    Walking it two lines at a time happens to stop correctly on an even-length block and
    steps over the blank line of an odd one, landing the rules in the project's own section.
    """

    gitignore = tmp_path / ".gitignore"
    gitignore.write_text(
        "# Agentic Discipline managed outputs\nartifacts/\n\n# mine\nnotes/\n",
        encoding="utf-8",
    )

    _update_gitignore(tmp_path, [], dry_run=False)

    assert gitignore.read_text(encoding="utf-8") == (
        "# Agentic Discipline managed outputs\n"
        "artifacts/\n"
        ".agent-memory/\n"
        ".agentic/verification/artifacts/\n"
        ".agentic/export/\n"
        ".agentic/control/\n"
        "\n"
        "# mine\n"
        "notes/\n"
    )


def test_an_empty_block_is_filled_in_place(tmp_path: Path) -> None:
    """A marker with nothing under it still owns the lines up to the blank that follows it."""

    gitignore = tmp_path / ".gitignore"
    gitignore.write_text(
        "# Agentic Discipline managed outputs\n\n# mine\nnotes/\n", encoding="utf-8"
    )

    _update_gitignore(tmp_path, [], dry_run=False)

    assert gitignore.read_text(encoding="utf-8") == (
        "# Agentic Discipline managed outputs\n"
        "artifacts/\n"
        ".agent-memory/\n"
        ".agentic/verification/artifacts/\n"
        ".agentic/export/\n"
        ".agentic/control/\n"
        "\n"
        "# mine\n"
        "notes/\n"
    )


def test_a_rule_the_project_already_ignores_elsewhere_is_not_repeated(tmp_path: Path) -> None:
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text(
        "artifacts/\n# Agentic Discipline managed outputs\n.agent-memory/\n",
        encoding="utf-8",
    )
    actions: list[str] = []

    _update_gitignore(tmp_path, actions, dry_run=False)

    assert gitignore.read_text(encoding="utf-8") == (
        "artifacts/\n"
        "# Agentic Discipline managed outputs\n"
        ".agent-memory/\n"
        ".agentic/verification/artifacts/\n"
        ".agentic/export/\n"
        ".agentic/control/\n"
    )
    assert actions == [
        f"UPDATE {gitignore} "
        "(added .agentic/verification/artifacts/, .agentic/export/, .agentic/control/)"
    ]


@pytest.mark.parametrize("configured", [False, True])
def test_the_projects_own_line_endings_are_kept(tmp_path: Path, configured: bool) -> None:
    """Writing through text mode on Windows would turn a whole LF file into CRLF.

    The reverse is what a CRLF project would see, so the block is written with the endings
    the file already uses, whichever machine runs `init`.
    """

    gitignore = tmp_path / ".gitignore"
    block = b"# Agentic Discipline managed outputs\r\nartifacts/\r\n" if configured else b""
    gitignore.write_bytes(b"dist/\r\n" + block)
    actions: list[str] = []

    _update_gitignore(tmp_path, actions, dry_run=False)

    written = gitignore.read_bytes()
    assert b"\r\n.agentic/control/\r\n" in written
    assert written.replace(b"\r\n", b"").count(b"\n") == 0


def test_rules_the_project_wrote_in_utf8_survive_the_update(tmp_path: Path) -> None:
    gitignore = tmp_path / ".gitignore"
    gitignore.write_bytes(
        "documentación/\n# Agentic Discipline managed outputs\nartifacts/\n".encode()
    )
    actions: list[str] = []

    _update_gitignore(tmp_path, actions, dry_run=False)

    written = gitignore.read_bytes().decode("utf-8")
    assert written.startswith("documentación/\n")
    assert written.endswith(".agentic/control/\n")


def test_dry_run_reports_the_update_without_writing(tmp_path: Path) -> None:
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("dist/\n", encoding="utf-8")
    actions: list[str] = []

    _update_gitignore(tmp_path, actions, dry_run=True)

    assert gitignore.read_text(encoding="utf-8") == "dist/\n"
    assert actions == [f"UPDATE {gitignore}"]
    _update_gitignore(tmp_path / "absent", actions, dry_run=True)
    assert not (tmp_path / "absent").exists()


def test_dry_run_reports_the_missing_rule_without_adding_it(tmp_path: Path) -> None:
    gitignore = tmp_path / ".gitignore"
    content = "# Agentic Discipline managed outputs\nartifacts/\n"
    gitignore.write_text(content, encoding="utf-8")
    actions: list[str] = []

    _update_gitignore(tmp_path, actions, dry_run=True)

    assert gitignore.read_text(encoding="utf-8") == content
    assert actions[0].startswith(f"UPDATE {gitignore} (added ")
    assert ".agentic/control/" in actions[0]
