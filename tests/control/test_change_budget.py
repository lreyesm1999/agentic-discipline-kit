"""Change budget, scope and protection checks, rule by rule.

`check_changes` is what stops a task from finishing when its edits exceed the
contract: too many files, files outside scope, protected paths or too many lines.
Existing tests hit each rule once through a full verification, so a boundary, the
scope prefix rule or the conservative line count could change unnoticed. Each case
edits a real project tree and pins the exact outcome.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline.control.contracts import ControlError
from agentic_discipline.control.discovery import fingerprint, line_counts, link_fingerprint
from agentic_discipline.control.verification import check_changes

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX symlinks")


def _write(root: Path, relative: str, lines: int) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"line {i}\n" for i in range(lines)), encoding="utf-8")


def _task(
    project: Any, scope: list[str], max_files: int = 10, max_lines: int = 1000
) -> dict[str, Any]:
    root = project.root
    return {
        "state": "CLAIMED",
        "scope": scope,
        "budget": {"max_files": max_files, "max_lines": max_lines},
        "initial_files": fingerprint(root),
        "initial_links": link_fingerprint(root),
        "initial_line_counts": line_counts(root, list(fingerprint(root))),
    }


def _refused(project: Any, task: dict[str, Any], code: str, message: str) -> None:
    with pytest.raises(ControlError) as caught:
        check_changes(project, task)
    assert (caught.value.code, str(caught.value)) == (code, message)


def test_no_changes_pass_even_without_recorded_baselines(project: Any) -> None:
    task = _task(project, ["src"])
    assert check_changes(project, task) is None
    bare = {"state": "CLAIMED", "scope": ["src"], "budget": {"max_files": 0, "max_lines": 0}}
    assert check_changes(project, bare) is None


def test_the_changed_file_budget_is_inclusive(project: Any) -> None:
    task = _task(project, ["."], max_files=2)
    _write(project.root, "src/a.py", 1)
    _write(project.root, "src/b.py", 1)
    assert check_changes(project, task) is None
    _write(project.root, "src/c.py", 1)
    _refused(project, task, "BUDGET_EXCEEDED", "Changed-file budget exceeded")


@pytest.mark.parametrize(
    ("scope", "path", "allowed"),
    [
        (["."], "anywhere/file.py", True),
        (["src"], "src/deep/file.py", True),
        (["src/"], "src/file.py", True),
        (["src/file.py"], "src/file.py", True),
        (["src"], "srcx/file.py", False),
        (["docs", "tests"], "src/file.py", False),
    ],
)
def test_every_change_must_fall_inside_the_scope(
    project: Any, scope: list[str], path: str, allowed: bool
) -> None:
    task = _task(project, scope)
    _write(project.root, path, 1)
    if allowed:
        assert check_changes(project, task) is None
    else:
        _refused(project, task, "SCOPE_EXCEEDED", "Changes outside task scope")


@pytest.mark.parametrize("target", ["AGENTS.md", ".agentic/notes.md"])
def test_protected_paths_and_their_contents_require_review(project: Any, target: str) -> None:
    assert {"AGENTS.md", ".agentic"} <= set(project.policy()["protected_paths"])
    task = _task(project, ["."])
    _write(project.root, target, 3)
    _refused(project, task, "PROTECTED_CHANGE", "Protected changes require review")


def test_protected_prefixes_do_not_match_sibling_names(project: Any) -> None:
    protected = project.policy()["protected_paths"][0].rstrip("/")
    task = _task(project, ["."])
    _write(project.root, protected + "-sibling/file.txt", 1)
    assert check_changes(project, task) is None


def test_line_budget_counts_the_larger_of_old_and_new_sizes(project: Any) -> None:
    _write(project.root, "src/shrinking.py", 30)
    _write(project.root, "src/deleted.py", 20)
    task = _task(project, ["src"], max_lines=35)
    _write(project.root, "src/shrinking.py", 5)
    (project.root / "src" / "deleted.py").unlink()
    _write(project.root, "src/new.py", 4)
    # 30 (shrinking, old size) + 20 (deleted) + 4 (new) = 54 lines.
    _refused(project, task, "BUDGET_EXCEEDED", "Conservative changed-file line budget exceeded")
    task["budget"]["max_lines"] = 54
    assert check_changes(project, task) is None


@posix_only
def test_changed_links_count_as_changes_but_not_as_lines(project: Any) -> None:
    _write(project.root, "src/target.py", 50)
    task = _task(project, ["src"], max_files=1, max_lines=0)
    (project.root / "src" / "link.py").symlink_to("target.py")
    assert check_changes(project, task) is None
    (project.root / "src" / "other.py").symlink_to("target.py")
    _refused(project, task, "BUDGET_EXCEEDED", "Changed-file budget exceeded")


def test_scope_prefixes_keep_every_character_of_the_directory_name(project: Any) -> None:
    task = _task(project, ["LibX"])
    _write(project.root, "LibX/module.py", 1)
    assert check_changes(project, task) is None


@posix_only
def test_links_already_in_the_baseline_are_not_changes(project: Any) -> None:
    _write(project.root, "src/target.py", 1)
    (project.root / "src" / "link.py").symlink_to("target.py")
    task = _task(project, ["src"], max_files=0, max_lines=0)
    assert check_changes(project, task) is None


def test_a_task_without_recorded_line_counts_counts_the_lines_now_present(project: Any) -> None:
    task = _task(project, ["src"], max_lines=3)
    del task["initial_line_counts"]
    _write(project.root, "src/new.py", 3)
    assert check_changes(project, task) is None
    _write(project.root, "src/new.py", 4)
    _refused(project, task, "BUDGET_EXCEEDED", "Conservative changed-file line budget exceeded")
