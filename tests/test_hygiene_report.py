"""Evolution hygiene report, field by field.

`hygiene` decides whether temporary files, unresolved deprecations and pending
removals block a change. The existing tests checked one removal and an invalid base
ref, so a lifecycle state could be misread, a temporary-file prefix could stop
matching, or one failure cause could stop failing the report unnoticed. Each case
compares the whole report.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agentic_discipline.common import run_git
from agentic_discipline.evolution import hygiene, register_lifecycle

EMPTY = {
    "status": "PASS",
    "temporary_artifacts": [],
    "unauthorized_fallbacks": [],
    "superseded_active": [],
    "stale_feature_flags": [],
    "orphan_tests": [],
    "stale_instructions": [],
    "unresolved_deprecations": [],
    "unresolved_removals": [],
    "new_temporary_artifacts": [],
}


def _repository(root: Path) -> Path:
    root.mkdir()
    run_git(["init", "-q"], cwd=root)
    run_git(["config", "user.name", "test"], cwd=root)
    run_git(["config", "user.email", "test@example.invalid"], cwd=root)
    (root / "app.py").write_text("value = 1\n", encoding="utf-8")
    run_git(["add", "."], cwd=root)
    run_git(["commit", "-q", "-m", "baseline"], cwd=root)
    return root


def _commit(root: Path, *paths: str) -> None:
    for relative in paths:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("pass\n", encoding="utf-8")
    run_git(["add", "."], cwd=root)
    run_git(["commit", "-q", "-m", "change"], cwd=root)


def test_clean_project_passes_with_an_empty_report(tmp_path: Path) -> None:
    root = _repository(tmp_path / "project")
    assert hygiene(root) == EMPTY
    assert hygiene(root, "HEAD") == EMPTY


def test_lifecycle_items_are_sorted_into_their_findings(tmp_path: Path) -> None:
    root = _repository(tmp_path / "project")
    (root / "old.py").write_text("pass\n", encoding="utf-8")
    items: list[dict[str, Any]] = [
        {"id": "TMP-1", "path": "scratch.py", "state": "TEMPORARY"},
        {"id": "DEP-1", "path": "legacy.py", "state": "DEPRECATE"},
        {"id": "DEP-2", "path": "legacy2.py", "state": "DEPRECATE", "removal_condition": "v3"},
        {"id": "REM-1", "path": "old.py", "state": "REMOVE"},
        {"id": "REM-2", "path": "gone.py", "state": "REMOVE"},
        {"id": "KEEP-1", "path": "app.py", "state": "KEEP"},
    ]
    for item in items:
        register_lifecycle(root, item)

    assert hygiene(root) == {
        **EMPTY,
        "status": "FAIL",
        "temporary_artifacts": [items[0]],
        "unresolved_deprecations": [items[1]],
        "unresolved_removals": ["REM-1"],
    }


def test_registered_temporary_artifacts_alone_do_not_fail(tmp_path: Path) -> None:
    root = _repository(tmp_path / "project")
    item = {"id": "TMP-1", "path": "scratch.py", "state": "TEMPORARY"}
    register_lifecycle(root, item)
    assert hygiene(root) == {**EMPTY, "temporary_artifacts": [item]}


@pytest.mark.parametrize(
    ("item", "field", "finding"),
    [
        (
            {"id": "DEP-1", "path": "legacy.py", "state": "DEPRECATE"},
            "unresolved_deprecations",
            None,
        ),
        ({"id": "REM-1", "path": "app.py", "state": "REMOVE"}, "unresolved_removals", "REM-1"),
    ],
)
def test_each_unresolved_lifecycle_finding_fails_on_its_own(
    tmp_path: Path, item: dict[str, Any], field: str, finding: Any
) -> None:
    root = _repository(tmp_path / "project")
    register_lifecycle(root, item)
    assert hygiene(root) == {**EMPTY, "status": "FAIL", field: [finding or item]}


def test_new_temporary_files_since_the_base_ref_fail(tmp_path: Path) -> None:
    root = _repository(tmp_path / "project")
    base = run_git(["rev-parse", "HEAD"], cwd=root).strip()
    _commit(
        root,
        "debug_probe.py",
        "tools/Inspect_state.py",
        "reproduce_bug.txt",
        "migration_helper_v2.py",
        "notes_debug_.py",
        "regular.py",
    )

    report = hygiene(root, base)

    added = report.pop("new_temporary_artifacts")
    assert sorted(added) == [
        "debug_probe.py",
        "migration_helper_v2.py",
        "reproduce_bug.txt",
        "tools/Inspect_state.py",
    ]
    assert report == {k: v for k, v in {**EMPTY, "status": "FAIL"}.items() if k in report}


def test_temporary_files_without_a_base_ref_are_not_inspected(tmp_path: Path) -> None:
    root = _repository(tmp_path / "project")
    _commit(root, "debug_probe.py")
    assert hygiene(root) == EMPTY


def test_an_unknown_base_ref_reports_no_changes(tmp_path: Path) -> None:
    root = _repository(tmp_path / "project")
    _commit(root, "debug_probe.py")
    assert hygiene(root, "no-such-ref") == EMPTY
