"""Adapter file emission: writes, managed regions and pruning.

Every agent surface is written through `Emission`, which must leave user-authored
content alone, report what it would do in a dry run, and remove only files it
generated. Existing tests synced real adapters, so the managed-region replacement,
the "already synchronized" check or the pruning rules could change unnoticed. Each
case compares the exact files and actions.
"""

from __future__ import annotations

from pathlib import Path

from agentic_discipline.adapters import GENERATED_PREFIX, MANAGED_END, MANAGED_START, Emission


def _body(block: str) -> str:
    return f"{MANAGED_START}\n\n{block}\n\n{MANAGED_END}"


# --- write ----------------------------------------------------------------------------------


def test_write_creates_updates_and_skips_identical_content(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "deeper" / "rules.md"
    emission = Emission()

    emission.write(path, "one\n")
    emission.write(path, "one\n")
    emission.write(path, "two\n")

    assert path.read_text(encoding="utf-8") == "two\n"
    assert emission.actions == [
        f"WRITE {path}",
        f"SKIP {path} (already synchronized)",
        f"UPDATE {path}",
    ]


def test_dry_run_reports_writes_without_touching_files(tmp_path: Path) -> None:
    new = tmp_path / "new" / "file.md"
    existing = tmp_path / "existing.md"
    existing.write_text("old\n", encoding="utf-8")
    emission = Emission(dry_run=True)

    emission.write(new, "content\n")
    emission.write(existing, "changed\n")

    assert not new.parent.exists()
    assert existing.read_text(encoding="utf-8") == "old\n"
    assert emission.actions == [f"WRITE {new}", f"UPDATE {existing}"]


# --- write_managed --------------------------------------------------------------------------


def test_managed_block_in_a_new_file_is_the_whole_file(tmp_path: Path) -> None:
    path = tmp_path / "AGENTS.md"
    Emission().write_managed(path, "Rules\n\n\n")
    assert path.read_text(encoding="utf-8") == _body("Rules") + "\n"


def test_managed_block_is_appended_after_user_content(tmp_path: Path) -> None:
    path = tmp_path / "AGENTS.md"
    path.write_text("# Team notes\n\nKeep this.\n\n\n", encoding="utf-8")
    Emission().write_managed(path, "Rules")
    assert (
        path.read_text(encoding="utf-8") == "# Team notes\n\nKeep this.\n\n" + _body("Rules") + "\n"
    )


def test_whitespace_only_files_get_no_separator(tmp_path: Path) -> None:
    path = tmp_path / "AGENTS.md"
    path.write_text("\n  \n", encoding="utf-8")
    Emission().write_managed(path, "Rules")
    assert path.read_text(encoding="utf-8") == _body("Rules") + "\n"


def test_only_the_managed_region_is_replaced(tmp_path: Path) -> None:
    path = tmp_path / "AGENTS.md"
    path.write_text(
        f"Before\n{MANAGED_START}\nold rules\n{MANAGED_END}\nAfter {MANAGED_END}\n",
        encoding="utf-8",
    )
    emission = Emission()

    emission.write_managed(path, "New rules")
    emission.write_managed(path, "New rules")

    assert path.read_text(encoding="utf-8") == (
        f"Before\n{_body('New rules')}\nAfter {MANAGED_END}\n"
    )
    assert emission.actions == [f"UPDATE {path}", f"SKIP {path} (already synchronized)"]


def test_an_unterminated_region_is_treated_as_user_content(tmp_path: Path) -> None:
    path = tmp_path / "AGENTS.md"
    path.write_text(f"{MANAGED_START}\nhalf written\n", encoding="utf-8")
    Emission().write_managed(path, "Rules")
    assert path.read_text(encoding="utf-8") == (
        f"{MANAGED_START}\nhalf written\n\n{_body('Rules')}\n"
    )


# --- prune ----------------------------------------------------------------------------------


def _generated(directory: Path) -> tuple[Path, Path, Path, Path]:
    kept_file = directory / f"{GENERATED_PREFIX}kept.md"
    stale_file = directory / f"{GENERATED_PREFIX}old.md"
    stale_dir = directory / f"{GENERATED_PREFIX}retired"
    user_file = directory / "handwritten.md"
    for path in (kept_file, stale_file, user_file):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")
    (stale_dir / "assets" / "deep").mkdir(parents=True)
    (stale_dir / "SKILL.md").write_text("x", encoding="utf-8")
    (stale_dir / "assets" / "deep" / "note.txt").write_text("x", encoding="utf-8")
    return kept_file, stale_file, stale_dir, user_file


def test_prune_removes_only_generated_entries_that_are_not_kept(tmp_path: Path) -> None:
    kept_file, stale_file, stale_dir, user_file = _generated(tmp_path / "rules")
    emission = Emission()

    emission.prune(tmp_path / "rules", {kept_file})

    assert kept_file.is_file() and user_file.is_file()
    assert not stale_file.exists() and not stale_dir.exists()
    assert emission.actions == [
        f"REMOVE {stale_file} (stale)",
        f"REMOVE {stale_dir / 'SKILL.md'} (stale)",
    ]


def test_prune_keeps_directories_whose_skill_file_is_kept(tmp_path: Path) -> None:
    _, stale_file, stale_dir, _ = _generated(tmp_path / "skills")
    emission = Emission()
    emission.prune(tmp_path / "skills", {stale_dir / "SKILL.md", stale_file})
    assert stale_dir.is_dir() and stale_file.is_file()
    assert emission.actions == [
        f"REMOVE {tmp_path / 'skills' / (GENERATED_PREFIX + 'kept.md')} (stale)"
    ]


def test_dry_run_prune_reports_without_removing(tmp_path: Path) -> None:
    kept_file, stale_file, stale_dir, _ = _generated(tmp_path / "rules")
    emission = Emission(dry_run=True)
    emission.prune(tmp_path / "rules", {kept_file})
    assert stale_file.is_file() and (stale_dir / "assets" / "deep" / "note.txt").is_file()
    assert len(emission.actions) == 2


def test_prune_of_a_missing_directory_does_nothing(tmp_path: Path) -> None:
    emission = Emission()
    emission.prune(tmp_path / "absent", set())
    assert emission.actions == []
