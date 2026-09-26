"""Exact words and branches the readiness mutation survivors still depend on.

Substring checks let a wrapped or re-cased string pass. Each assertion here is the whole
value the mutant changes, on the branch that produces it.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline import __version__, readiness
from agentic_discipline.bootstrap import PAYLOAD_SCHEMA, initialize_project
from agentic_discipline.common import AgenticError, run_git
from agentic_discipline.control.plane import adopt
from agentic_discipline.readiness import Check


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    initialize_project(root, adopt=False)
    run_git(["init"], cwd=root)
    return root


def _checkout(tmp_path: Path) -> Path:
    root = tmp_path / "kit"
    (root / "disciplines" / "01-source").mkdir(parents=True)
    (root / "config" / "profiles").mkdir(parents=True)
    (root / "disciplines" / "01-source" / "SKILL.md").write_text("x\n", encoding="utf-8")
    (root / "AGENTS.md").write_text("# kit\n", encoding="utf-8")
    return root


def _check(name: str, status: str, detail: str, **kwargs: Any) -> Check:
    return Check(name, status, detail, **kwargs)


def test_shape_needs_every_checkout_marker_and_the_real_config_name(tmp_path: Path) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    assert readiness.shape(root) == "absent"
    (root / "config" / "profiles").mkdir(parents=True)
    assert readiness.shape(root) == "absent"
    (root / "disciplines").mkdir()
    assert readiness.shape(root) == "absent"
    (root / "AGENTS.md").write_text("# kit\n", encoding="utf-8")
    assert readiness.shape(root) == "checkout"
    bare = tmp_path / "bare"
    bare.mkdir()
    (bare / "agentic.config.json").write_text("{}\n", encoding="utf-8")
    assert readiness.shape(bare) == "project"


def test_an_incomplete_installation_names_each_missing_file(tmp_path: Path) -> None:
    root = tmp_path / "half"
    root.mkdir()
    (root / "agentic.config.json").write_text("{}\n", encoding="utf-8")
    check = readiness._installation(root, "project")
    assert (check.name, check.status, check.repair) == (
        "installation",
        "MISSING",
        "agentic-discipline init --force",
    )
    assert check.detail == "the installation is incomplete: AGENTS.md, MASTER_PROMPT.md, schemas"
    assert "schemas" in check.detail
    assert "SCHEMAS" not in check.detail and "XXschemasXX" not in check.detail


def test_a_complete_project_reports_the_kit_version(tmp_path: Path) -> None:
    root = _project(tmp_path)
    check = readiness._installation(root, "project")
    assert (check.name, check.status, check.detail, check.repair) == (
        "installation",
        "PASS",
        f"version {__version__}",
        None,
    )


def test_version_pins_each_schema_outcome(tmp_path: Path) -> None:
    root = _project(tmp_path)
    absent = readiness._version(tmp_path / "nope", "absent")
    assert (absent.name, absent.status, absent.detail) == ("version", "PASS", f"kit {__version__}")

    current = readiness._version(root, "project")
    assert (current.name, current.status) == ("version", "PASS")
    assert current.detail == f"kit {__version__}, payload schema {PAYLOAD_SCHEMA}"

    payload = root / ".agentic" / "config.json"
    payload.write_text("{", encoding="utf-8")
    broken = readiness._version(root, "project")
    assert broken.detail == f"kit {__version__}, payload schema {PAYLOAD_SCHEMA}"

    payload.write_text(json.dumps({"schema_version": "99"}), encoding="utf-8")
    newer = readiness._version(root, "project")
    assert (newer.name, newer.status) == ("version", "FAIL")
    assert newer.detail == (
        "the payload is schema 99 and this kit installs "
        f"{PAYLOAD_SCHEMA}: upgrade the kit rather than downgrading the project"
    )

    payload.write_text(json.dumps({"schema_version": "1"}), encoding="utf-8")
    older = readiness._version(root, "project")
    assert (older.name, older.status) == ("version", "FAIL")
    assert "run `agentic-discipline migrate`" in older.detail

    (root / "policies").mkdir()
    payload.write_text(json.dumps({"schema_version": PAYLOAD_SCHEMA}), encoding="utf-8")
    stale = readiness._version(root, "project")
    assert stale.status == "STALE"
    assert (stale.name, stale.status, stale.repair) == (
        "version",
        "STALE",
        "agentic-discipline migrate --prune",
    )
    assert stale.detail.startswith("an earlier layout is still in the repository root: policies")


def test_disciplines_name_the_gap_and_the_repair(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    root.mkdir()
    empty = readiness._disciplines(root)
    assert (empty.name, empty.status, empty.detail, empty.repair) == (
        "disciplines",
        "MISSING",
        "no disciplines are installed",
        "agentic-discipline init",
    )
    skill = root / "disciplines" / "01-only"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("x\n", encoding="utf-8")
    short = readiness._disciplines(root)
    assert (short.name, short.status, short.repair) == (
        "disciplines",
        "STALE",
        "agentic-discipline init --force",
    )
    assert short.detail == f"1 disciplines installed, {readiness.EXPECTED_DISCIPLINES} expected"


def test_agent_adapter_reports_pending_files_and_current_labels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)

    def pending(root: Path, adapters: object, dry_run: bool = False) -> dict[str, Any]:
        assert adapters == ["cursor"]
        assert dry_run is True
        return {"actions": ["WRITE agents.md"], "labels": ["cursor", "copilot"]}

    monkeypatch.setattr("agentic_discipline.adapters.detect_adapters", lambda root: ["cursor"])
    monkeypatch.setattr("agentic_discipline.adapters.sync_adapters", pending)
    check = readiness._agent_adapter(root, "project")
    assert (check.name, check.status, check.repair) == (
        "agent_adapter",
        "STALE",
        "agentic-discipline adapters sync",
    )
    assert check.detail == "1 generated file(s) differ from the current disciplines"

    def current(root: Path, adapters: object, dry_run: bool = False) -> dict[str, Any]:
        assert adapters == ["cursor"]
        return {"actions": ["SKIP agents.md"], "labels": ["cursor", "copilot"]}

    monkeypatch.setattr("agentic_discipline.adapters.sync_adapters", current)
    passed = readiness._agent_adapter(root, "project")
    assert (passed.status, passed.detail) == ("PASS", "cursor, copilot")


def test_quality_gates_read_the_example_and_a_broken_file(tmp_path: Path) -> None:
    root = tmp_path / "gates"
    root.mkdir()
    initialize_project(root, adopt=False)
    (root / "agentic.config.json").replace(root / "agentic.config.example.json")
    passed = readiness._quality_gates(root, None)
    assert (passed.name, passed.status, passed.detail) == (
        "quality_gates",
        "PASS",
        "1 gates in agentic.config.example.json",
    )

    def boom(path: Path) -> dict[str, Any]:
        raise AgenticError("not json")

    broken = root / "agentic.config.json"
    broken.write_text("{", encoding="utf-8")
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("agentic_discipline.validation.load_quality_config", boom)
    try:
        failed = readiness._quality_gates(root, broken)
    finally:
        monkeypatch.undo()
    assert (failed.name, failed.status, failed.detail) == ("quality_gates", "FAIL", "not json")


def test_an_unopenable_database_names_the_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _project(tmp_path)
    adopt(root)

    def refuse(database: Path) -> Any:
        raise AgenticError("locked")

    monkeypatch.setattr("agentic_discipline.control.store.Store", refuse)
    check, store = readiness._control_plane(root, "project", "managed")
    assert store is None
    assert check.name == "control_plane"
    assert check.status == "FAIL"
    assert check.detail == "the state database cannot be opened: locked"


def test_project_adoption_and_knowledge_name_a_missing_plane(tmp_path: Path) -> None:
    adoption = readiness._project_adoption(tmp_path, None)
    assert (adoption.name, adoption.status, adoption.detail, adoption.caused_by) == (
        "project_adoption",
        "MISSING",
        "no project record, because there is no control plane",
        "control_plane",
    )
    knowledge = readiness._knowledge(tmp_path, None, deep=False)
    assert (knowledge.name, knowledge.status, knowledge.detail, knowledge.caused_by) == (
        "knowledge",
        "MISSING",
        "no knowledge store, because there is no control plane",
        "control_plane",
    )


def test_knowledge_counts_code_files_and_not_symbols(tmp_path: Path) -> None:
    class Store:
        def list(self, kind: str) -> list[dict[str, Any]]:
            assert kind == "entity" or kind == "project"
            if kind == "project":
                return []
            return [
                {"graph": "code", "path": "src/app.py"},
                {"graph": "code", "path": "src/app.py", "symbol_type": "function"},
                {"graph": "requirement", "path": "specs/requirements.md"},
            ]

    check = readiness._knowledge(tmp_path, Store(), deep=False)
    assert (check.name, check.status, check.detail) == ("knowledge", "PASS", "1 files indexed")


def test_an_unscannable_tree_is_a_knowledge_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Store:
        def list(self, kind: str) -> list[dict[str, Any]]:
            if kind == "entity":
                return [{"graph": "code", "path": "src/app.py"}]
            return []

    def boom(root: Path) -> dict[str, Any]:
        raise OSError("denied")

    monkeypatch.setattr("agentic_discipline.control.discovery.scan", boom)
    check = readiness._knowledge(tmp_path, Store(), deep=True)
    assert check.name == "knowledge"
    assert check.status == "FAIL"
    assert check.detail == "the working tree cannot be scanned: denied"


def test_task_orchestration_counts_open_work(tmp_path: Path) -> None:
    class Bare:
        def list(self, kind: str) -> list[object]:
            assert kind == "policy"
            return []

    no_policy = readiness._task_orchestration(Bare())
    assert (no_policy.name, no_policy.status, no_policy.detail, no_policy.repair) == (
        "task_orchestration",
        "MISSING",
        "no execution policy is recorded",
        "agentic adopt",
    )
    missing = readiness._task_orchestration(None)
    assert (missing.name, missing.status, missing.detail, missing.caused_by) == (
        "task_orchestration",
        "MISSING",
        "tasks, leases and checkpoints need the control plane",
        "control_plane",
    )
    root = _project(tmp_path)
    adopt(root)
    from agentic_discipline.control.plane import Plane

    with Plane(root) as plane:
        with plane.store.transaction():
            plane.store.put("task", {"objective": "open", "state": "READY", "scope": []})
            plane.store.put("task", {"objective": "done", "state": "COMPLETED", "scope": []})
            plane.store.put("task", {"objective": "dropped", "state": "CANCELLED", "scope": []})
        counted = readiness._task_orchestration(plane.store)
    assert (counted.name, counted.status, counted.detail) == (
        "task_orchestration",
        "PASS",
        "3 tasks, 1 open",
    )


def test_git_missing_is_a_failure_with_that_sentence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    check = readiness._git_integration(tmp_path)
    assert (check.name, check.status, check.detail, check.repair) == (
        "git_integration",
        "FAIL",
        "git is not installed",
        None,
    )


def test_group_fails_only_on_fail_and_passes_only_pass_or_off() -> None:
    def group(*pairs: tuple[str, str]) -> str:
        by_name = {name: Check(name, status, "detail") for name, status in pairs}
        return readiness._group(by_name, tuple(name for name, _status in pairs))

    assert group(("installation", "FAIL")) == "FAIL"
    assert group(("installation", "PASS"), ("version", "OFF")) == "PASS"
    assert group(("installation", "MISSING")) == "PARTIAL"
    assert group(("installation", "PASS"), ("version", "STALE")) == "PARTIAL"


def test_verdict_uses_the_root_and_the_exact_reason(tmp_path: Path) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    checks = [
        Check(name, "PASS", "ok")
        for name in (
            *readiness.INSTALLATION_CHECKS,
            *readiness.PROJECT_CHECKS,
            *readiness.ENVIRONMENT_CHECKS,
        )
    ]
    # Absent is decided from the shape argument, before any failing check.
    verdict = readiness._verdict(root, "absent", "managed", checks)
    assert verdict["root"] == str(root)
    assert verdict["reason"] == "Agentic Discipline is not installed in this directory"
    assert verdict["status"] == "FAIL"
    assert verdict["execution_readiness"] == "NOT_INITIALIZED"

    ready = readiness._verdict(root, "project", "managed", checks)
    assert ready["status"] == "PASS"
    assert ready["reason"] == "every check passes; the full workflow is available"

    off = [
        Check("control_plane", "OFF", "orchestration is off on purpose")
        if check.name == "control_plane"
        else check
        for check in checks
    ]
    degraded = readiness._verdict(root, "project", "rules-only", off)
    assert degraded["status"] == "FAIL"
    assert degraded["reason"] == "orchestration is off on purpose"

    unrepairable = [
        Check("installation", "MISSING", "gone") if check.name == "installation" else check
        for check in checks
    ]
    partial = readiness._verdict(root, "project", "managed", unrepairable)
    assert partial["execution_readiness"] == "PARTIAL"
    assert partial["reason"] == "Installation: gone"

    drifted = [
        Check("git_integration", "MISSING", "no tree", advisory=True)
        if check.name == "git_integration"
        else check
        for check in checks
    ]
    advisory = readiness._verdict(root, "project", "managed", drifted)
    assert advisory["status"] == "PASS"
    assert advisory["drift"] == ["git_integration"]
    assert advisory["execution_readiness"] == "READY"


def test_inspect_passes_the_resolved_root(tmp_path: Path) -> None:
    report = readiness.inspect(tmp_path, deep=False)
    assert report["root"] == str(tmp_path.resolve())
    assert report["reason"] == "Agentic Discipline is not installed in this directory"
    assert report["status"] == "FAIL"


def test_installation_recognizes_root_schemas_directory(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "AGENTS.md").write_text("x", encoding="utf-8")
    (root / "MASTER_PROMPT.md").write_text("x", encoding="utf-8")
    (root / "schemas").mkdir()
    check = readiness._installation(root, "project")
    assert check.status == "PASS"
    assert check.name == "installation"
    assert check.detail == f"version {__version__}"
    assert check.repair is None
    # Windows is case-insensitive, but let's test a non-matching name
    (root / "schemas").rename(root / "other_schemas")
    other_check = readiness._installation(root, "project")
    assert other_check.status == "MISSING"


def test_control_plane_database_open_failure_returns_exact_check(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".agentic" / "control").mkdir(parents=True)
    (root / ".agentic" / "control" / "state.db").write_bytes(b"corrupt")
    check, store = readiness._control_plane(root, "project", "managed")
    assert store is None
    assert check.name == "control_plane"
    assert check.status == "FAIL"
    assert check.detail.startswith("the state database cannot be opened: ")
    assert check.detail == (
        "the state database cannot be opened: "
        f"{check.detail.removeprefix('the state database cannot be opened: ')}"
    )


def test_knowledge_and_adoption_check_names_are_exact(tmp_path: Path) -> None:
    class DummyStore:
        def list(self, kind: str) -> list[dict[str, Any]]:
            if kind == "entity":
                return [{"graph": "code", "path": "src/app.py"}]
            if kind == "project":
                return [{"name": "proj", "root": str(tmp_path)}]
            return []

    store = DummyStore()
    k_check = readiness._knowledge(tmp_path, store, deep=False)
    assert k_check.name == "knowledge"
    assert k_check.status == "PASS"

    p_check = readiness._project_adoption(tmp_path, store)
    assert p_check.name == "project_adoption"
    assert p_check.status == "PASS"


def test_verdict_advisory_pass_does_not_count_as_drift(tmp_path: Path) -> None:
    checks = [
        Check(name, "PASS", "ok", advisory=(name == "git_integration"))
        for name in (
            *readiness.INSTALLATION_CHECKS,
            *readiness.PROJECT_CHECKS,
            *readiness.ENVIRONMENT_CHECKS,
        )
    ]
    verdict = readiness._verdict(tmp_path, "project", "managed", checks)
    assert verdict["drift"] == []
    assert verdict["execution_readiness"] == "READY"


def test_verdict_failed_reason_is_populated(tmp_path: Path) -> None:
    checks = [
        Check(name, "FAIL" if name == "installation" else "PASS", "missing installation")
        for name in (
            *readiness.INSTALLATION_CHECKS,
            *readiness.PROJECT_CHECKS,
            *readiness.ENVIRONMENT_CHECKS,
        )
    ]
    verdict = readiness._verdict(tmp_path, "project", "managed", checks)
    assert verdict["execution_readiness"] == "BROKEN"
    assert verdict["reason"] == "Installation: missing installation"


def test_inspect_fails_on_newer_schema_when_shape_is_project(tmp_path: Path) -> None:
    root = _project(tmp_path)
    payload = root / ".agentic" / "config.json"
    payload.write_text(json.dumps({"schema_version": "99"}), encoding="utf-8")
    report = readiness.inspect(root, deep=False)
    v_check = next(c for c in report["checks"] if c["name"] == "version")
    assert v_check["status"] == "FAIL"


def test_check_report_includes_caused_by_key() -> None:
    check = Check("knowledge", "MISSING", "no store", caused_by="control_plane")
    rep = check.report()
    assert "caused_by" in rep
    assert rep["caused_by"] == "control_plane"


def test_version_reads_utf8_config(tmp_path: Path) -> None:
    root = _project(tmp_path)
    payload = root / ".agentic" / "config.json"
    payload.write_text(json.dumps({"schema_version": PAYLOAD_SCHEMA, "desc": "diseño y gestión"}), encoding="utf-8")
    check = readiness._version(root, "project")
    assert check.status == "PASS"


def test_inspect_calls_version_with_exact_kind(tmp_path: Path) -> None:
    root = tmp_path / "absent_tree"
    root.mkdir()
    report = readiness.inspect(root, deep=False)
    v_check = next(c for c in report["checks"] if c["name"] == "version")
    assert v_check["status"] == "PASS"
    assert v_check["detail"] == f"kit {__version__}"


def test_knowledge_missing_check_name_is_exact(tmp_path: Path) -> None:
    check = readiness._knowledge(tmp_path, None, deep=False)
    assert check.name == "knowledge"
    assert check.status == "MISSING"


def test_project_adoption_missing_check_name_is_exact(tmp_path: Path) -> None:
    check = readiness._project_adoption(tmp_path, None)
    assert check.name == "project_adoption"
    assert check.status == "MISSING"


def test_knowledge_scanned_failure_name_is_exact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeStore:
        def list(self, kind: str) -> list[dict[str, Any]]:
            if kind == "entity":
                return [{"graph": "code", "path": "src/app.py"}]
            return []

    monkeypatch.setattr(
        "agentic_discipline.control.discovery.scan",
        lambda root: (_ for _ in ()).throw(AgenticError("disk full")),
    )
    check = readiness._knowledge(tmp_path, FakeStore(), deep=True)
    assert check.name == "knowledge"
    assert check.status == "FAIL"
    assert "disk full" in check.detail


