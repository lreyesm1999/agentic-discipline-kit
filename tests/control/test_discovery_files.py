"""Discovery file listing and area classification, path by path.

`files` decides which paths the control plane measures and indexes, and `area` labels
each one for coverage reports. Existing tests saw them only through full scans, so a
gitignored file could be measured, a deleted file listed, a scope prefix could match
a sibling directory, or a path could land in the wrong area unnoticed. Each case
states the exact list or label.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from agentic_discipline.common import run_git
from agentic_discipline.control.discovery import area, files

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX symlinks")


def _write(root: Path, *paths: str) -> None:
    for relative in paths:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x\n", encoding="utf-8")


def _names(listed: list[Path]) -> list[str]:
    return [path.as_posix() for path in listed]


LAYOUT = (
    "app.py",
    "src/pkg/mod.py",
    "src/pkg/data.json",
    "srcx/other.py",
    "docs/guide.md",
    "node_modules/pkg/index.js",
    ".env",
    "keys/server.pem",
    "build/cache.pyc",
)


def test_without_git_every_measured_file_is_listed_sorted(tmp_path: Path) -> None:
    _write(tmp_path, *LAYOUT)
    assert _names(files(tmp_path)) == [
        "app.py",
        "docs/guide.md",
        "src/pkg/data.json",
        "src/pkg/mod.py",
        "srcx/other.py",
    ]


@pytest.mark.parametrize(
    ("scope", "expected"),
    [
        (
            ["."],
            ["app.py", "docs/guide.md", "src/pkg/data.json", "src/pkg/mod.py", "srcx/other.py"],
        ),
        (["src"], ["src/pkg/data.json", "src/pkg/mod.py"]),
        (["src/"], ["src/pkg/data.json", "src/pkg/mod.py"]),
        (["src/pkg/mod.py", "app.py"], ["app.py", "src/pkg/mod.py"]),
        (["LibX"], []),
        ([], []),
    ],
)
def test_scope_selects_exact_files_and_directory_prefixes(
    tmp_path: Path, scope: list[str], expected: list[str]
) -> None:
    _write(tmp_path, *LAYOUT)
    assert _names(files(tmp_path, scope=scope)) == expected


def test_scope_prefixes_keep_every_character_of_the_directory_name(tmp_path: Path) -> None:
    _write(tmp_path, "LibX/a.py", "Lib/b.py")
    assert _names(files(tmp_path, scope=["LibX"])) == ["LibX/a.py"]


def test_git_listing_honours_ignore_rules_and_skips_deleted_files(tmp_path: Path) -> None:
    run_git(["init", "-q"], cwd=tmp_path)
    run_git(["config", "user.email", "test@example.invalid"], cwd=tmp_path)
    run_git(["config", "user.name", "test"], cwd=tmp_path)
    _write(tmp_path, "app.py", "gone.py", "generated/out.py", "notes.md")
    (tmp_path / ".gitignore").write_text("generated/\n", encoding="utf-8")
    run_git(["add", "app.py", "gone.py", ".gitignore"], cwd=tmp_path)
    run_git(["commit", "-q", "-m", "baseline"], cwd=tmp_path)
    (tmp_path / "gone.py").unlink()

    assert _names(files(tmp_path)) == [".gitignore", "app.py", "notes.md"]
    assert _names(files(tmp_path, include_ignored=True)) == [
        ".gitignore",
        "app.py",
        "generated/out.py",
        "notes.md",
    ]


@posix_only
def test_symlinked_files_and_directories_are_never_listed(tmp_path: Path) -> None:
    root = tmp_path / "project"
    _write(root, "app.py")
    outside = tmp_path / "outside"
    _write(outside, "secret.py")
    (root / "linked-dir").symlink_to(outside, target_is_directory=True)
    (root / "linked.py").symlink_to(root / "app.py")
    assert _names(files(root)) == ["app.py"]
    assert _names(files(root, include_ignored=True)) == ["app.py"]


@pytest.mark.parametrize(
    ("path", "label"),
    [
        ("AGENTS.md", "agent_instructions"),
        ("CLAUDE.md", "agent_instructions"),
        ("docs/GEMINI.md", "agent_instructions"),
        ("skills/test_skill/SKILL.md", "agent_instructions"),
        (".github/workflows/test.yml", "ci"),
        ("docs/testing.md", "tests"),
        ("Tests/Unit.py", "tests"),
        ("src/contest.py", "tests"),
        ("README.md", "docs"),
        ("notes.rst", "docs"),
        ("changes.txt", "docs"),
        ("db/migration/001.py", "persistence"),
        ("db/Migration/001.py", "source"),
        ("schema.sql", "persistence"),
        ("settings.json", "config"),
        ("pyproject.toml", "config"),
        ("compose.yaml", "config"),
        ("ci.yml", "config"),
        ("setup.ini", "config"),
        ("src/app.py", "source"),
        ("Makefile", "source"),
    ],
)
def test_area_labels_each_path_by_first_matching_rule(path: str, label: str) -> None:
    assert area(Path(path)) == label
