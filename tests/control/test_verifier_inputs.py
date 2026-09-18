"""Verifier input validation, path by path.

`validate_inputs` stops a verifier from claiming freshness for data the control
plane does not measure: excluded paths and anything reached through a symlink.
Existing tests hit it only through full verification runs, so an excluded name, a
symlinked parent or a scope prefix could stop being refused unnoticed. Each case
states which inputs pass and which are refused with which message.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from agentic_discipline.control.contracts import ControlError
from agentic_discipline.control.discovery import validate_inputs

EXCLUDED = "Verifier input is excluded from measurement"
FOLLOWS = "Verifier inputs cannot follow symlinks"
CONTAINS = "Symlink in verifier inputs; use contained, measured files"
posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX symlinks")


def _tree(root: Path) -> Path:
    for relative in ("src/app.py", "srcx/other.py", "docs/guide.md", "node_modules/pkg/index.js"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n", encoding="utf-8")
    return root


def _refuses(root: Path, scope: list[str], message: str) -> None:
    with pytest.raises(ControlError) as caught:
        validate_inputs(root, scope)
    assert (caught.value.code, str(caught.value)) == ("UNTRACKED_INPUT", message)


def test_measured_inputs_pass(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    assert validate_inputs(root, ["."]) is None
    assert validate_inputs(root, ["src/app.py", "docs/", "missing.py"]) is None
    assert validate_inputs(root, []) is None


@pytest.mark.parametrize(
    "value",
    [
        "node_modules/pkg/index.js",
        "artifacts/report.json",
        ".env",
        ".env.local",
        "keys/server.pem",
        "build.pyc",
        "pkg.egg-info/PKG-INFO",
        ".agentic/control/state.db",
        ".agentic/adopt-123/state.db",
    ],
)
def test_excluded_inputs_are_refused(tmp_path: Path, value: str) -> None:
    _refuses(_tree(tmp_path), ["src/app.py", value], EXCLUDED)


def test_unmeasured_agentic_payload_outside_control_is_allowed(tmp_path: Path) -> None:
    assert validate_inputs(_tree(tmp_path), [".agentic/config.json"]) is None


@posix_only
def test_inputs_reached_through_a_symlinked_parent_are_refused(tmp_path: Path) -> None:
    root = _tree(tmp_path / "project")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "data.txt").write_text("secret\n", encoding="utf-8")
    (root / "linked").symlink_to(outside, target_is_directory=True)
    _refuses(root, ["linked/data.txt"], FOLLOWS)
    _refuses(root, ["linked"], FOLLOWS)


@posix_only
@pytest.mark.parametrize("scope", [["."], ["src"], ["src/"], ["src/nested/link.py"]])
def test_symlinks_inside_the_scope_are_refused(tmp_path: Path, scope: list[str]) -> None:
    root = _tree(tmp_path)
    (root / "src" / "nested").mkdir()
    (root / "src" / "nested" / "link.py").symlink_to(root / "src" / "app.py")
    expected = FOLLOWS if scope == ["src/nested/link.py"] else CONTAINS
    _refuses(root, scope, expected)


@posix_only
def test_symlinks_outside_the_scope_or_in_excluded_trees_are_ignored(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    (root / "srcx" / "link.py").symlink_to(root / "src" / "app.py")
    (root / "node_modules" / "pkg" / "link.js").symlink_to(root / "src" / "app.py")
    assert validate_inputs(root, ["src"]) is None
    assert validate_inputs(root, ["docs", "src/app.py"]) is None
    _refuses(root, ["."], CONTAINS)


@posix_only
def test_symlinked_directories_are_refused_but_never_walked(tmp_path: Path) -> None:
    root = _tree(tmp_path / "project")
    outside = tmp_path / "outside"
    (outside / "deep").mkdir(parents=True)
    (outside / "deep" / "loop").symlink_to(outside, target_is_directory=True)
    (root / "docs" / "external").symlink_to(outside, target_is_directory=True)
    _refuses(root, ["docs"], CONTAINS)
    assert validate_inputs(root, ["src"]) is None


@posix_only
def test_scope_prefixes_keep_every_character_of_the_directory_name(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    (root / "LibX").mkdir()
    (root / "LibX" / "link.py").symlink_to(root / "src" / "app.py")
    _refuses(root, ["LibX"], CONTAINS)
    _refuses(root, ["LibX/"], CONTAINS)
