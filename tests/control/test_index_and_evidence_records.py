"""Records written by adoption, discovery indexing and verification.

Adoption seeds the project and policy, indexing turns scanned files into file and
symbol entities, and verification persists evidence and its output artifact.
Other code and agents rely on every field of these records, but tests only read a
few of them. Each case compares the records field by field, including what must
become historical and what must never be recorded.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import pytest
from conftest import checkpoint, contract

from agentic_discipline.common import run_git
from agentic_discipline.control.contracts import ControlError, digest
from agentic_discipline.control.discovery import scan
from agentic_discipline.control.plane import Plane, adopt
from agentic_discipline.control.verification import binding, verify

APP = (
    "import os\n"
    "\n"
    "class Service:\n"
    "    def run(self):\n"
    "        return os.sep\n"
    "\n"
    "def helper():\n"
    "    return 1\n"
    "\n"
    "def helper():\n"
    "    return 2\n"
)
POLICY = {
    "allowed_commands": [],
    "protected_paths": [
        ".agentic",
        "AGENTS.md",
        "MASTER_PROMPT.md",
        "agentic.config.json",
        "agentic.config.example.json",
        "schemas",
        "skills",
        "disciplines",
        "specs",
        "acceptance",
        "architecture",
        "policies",
        ".github/workflows",
    ],
    "max_lease_seconds": 3600,
    "network": False,
    "production": False,
}


def _repository(root: Path) -> Path:
    root.mkdir()
    (root / "app.py").write_text(APP)
    (root / "notes.md").write_text("# Notes\n")
    run_git(["init"], cwd=root)
    run_git(["config", "user.name", "Index Test"], cwd=root)
    run_git(["config", "user.email", "index@example.invalid"], cwd=root)
    run_git(["add", "."], cwd=root)
    run_git(["commit", "-m", "baseline"], cwd=root)
    return root


def _strip(record: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in record.items() if k not in {"id", "version"}}


def _entities(plane: Plane, **match: Any) -> list[dict[str, Any]]:
    return [
        e
        for e in plane.store.list("entity")
        if all(e.get(key) == value for key, value in match.items())
    ]


def _force(plane: Any, kind: str, identifier: str, **fields: Any) -> dict[str, Any]:
    """Put a record into a state that is expensive to reach through the workflow."""
    with plane.store.transaction():
        current = plane.store.get(identifier, kind)
        return plane.store.put(kind, {**current, **fields}, expected=current["version"])


# --- adopt --------------------------------------------------------------------------------


def test_dry_run_reports_the_scan_and_writes_nothing(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo")
    assert adopt(root, dry_run=True) == {
        **scan(root.resolve()),
        "dry_run": True,
        "writes": [".agentic/control/state.db"],
    }
    assert not (root / ".agentic").exists()


def test_adoption_records_project_policy_and_summary(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo").resolve()
    report = scan(root)

    assert adopt(root) == {
        "adopted": True,
        "coverage": report["coverage"],
        "stacks": report["stacks"],
        "files": len(report["files"]),
        "runtime": "UNKNOWN",
        "writes": [".agentic/control/state.db"],
    }
    control = root / ".agentic" / "control"
    assert not [p for p in control.parent.iterdir() if p.name.startswith("adopt-")]
    if os.name == "posix":
        assert (control.stat().st_mode & 0o777, (control / "state.db").stat().st_mode & 0o777) == (
            0o700,
            0o600,
        )

    with Plane(root) as plane:
        (project,) = plane.store.list("project")
        assert {
            k: project[k] for k in ("name", "root", "baseline_commit", "baseline_fingerprint")
        } == {
            "name": root.name,
            "root": str(root),
            "baseline_commit": report["commit"],
            "baseline_fingerprint": report["fingerprint"],
        }
        assert (project["coverage"], project["stacks"]) == (report["coverage"], report["stacks"])
        assert _strip(plane.policy()) == POLICY


def test_adopting_twice_reports_the_existing_project(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo")
    adopt(root)
    again = adopt(root)
    assert again["already_adopted"] is True
    with Plane(root) as plane:
        assert {k: v for k, v in again.items() if k != "already_adopted"} == plane.status()


def test_unmanaged_control_directory_is_not_overwritten(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo")
    (root / ".agentic" / "control").mkdir(parents=True)
    (root / ".agentic" / "control" / "notes.txt").write_text("hand-made\n")
    with pytest.raises(ControlError) as caught:
        adopt(root)
    assert (caught.value.code, str(caught.value)) == (
        "UNMANAGED_STATE",
        "Control directory already exists; inspect it before adoption",
    )
    assert (root / ".agentic" / "control" / "notes.txt").read_text() == "hand-made\n"


# --- _index and _index_symbols -----------------------------------------------------------


def test_index_records_file_and_symbol_entities(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo").resolve()
    report = scan(root)
    adopt(root)
    item = next(f for f in report["files"] if f["path"] == "app.py")

    with Plane(root) as plane:
        (file_entity,) = _entities(plane, type="file", source_ref="app.py")
        assert _strip(file_entity) == {
            "graph": "code",
            "type": "file",
            "name": "app.py",
            "source_ref": "app.py",
            "authority": "code",
            "confidence": 1,
            "observation": "OBSERVED",
            "lifecycle": "ACTIVE",
            "stale": False,
            **item,
        }

        symbols = sorted(
            _entities(plane, type="symbol", file_id=file_entity["id"]),
            key=lambda s: (s["line"], s["name"]),
        )
        assert [_strip(s) for s in symbols] == [
            {
                "graph": "code",
                "type": "symbol",
                "name": name,
                "symbol_type": symbol_type,
                "occurrence": occurrence,
                "file_id": file_entity["id"],
                "line": line,
                "source_ref": "app.py",
                "content_hash": item["content_hash"],
                "authority": "code",
                "observation": "OBSERVED",
                "confidence": 1,
                "lifecycle": "ACTIVE",
                "stale": False,
            }
            for name, symbol_type, occurrence, line in (
                ("Service", "ClassDef", 0, 3),
                ("Service.run", "FunctionDef", 0, 4),
                ("helper", "FunctionDef", 0, 7),
                ("helper", "FunctionDef", 1, 10),
            )
        ]
        edges = {
            (row["source"], row["target"], row["relation"])
            for row in plane.store.db.execute("SELECT source, target, relation FROM edges")
        }
        assert {(file_entity["id"], s["id"], "contains") for s in symbols} <= edges


def test_reindexing_keeps_identities_and_retires_what_disappeared(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo").resolve()
    adopt(root)
    with Plane(root) as plane:
        (app,) = _entities(plane, type="file", source_ref="app.py")
        before = {
            (s["name"], s["occurrence"]): s
            for s in _entities(plane, type="symbol", file_id=app["id"])
        }
        (notes,) = _entities(plane, type="file", source_ref="notes.md")

        # Drop the method and the second helper, rename notes.md without changing it.
        (root / "app.py").write_text("class Service:\n    pass\n\ndef helper():\n    return 1\n")
        (root / "notes.md").rename(root / "readme_notes.md")
        version = plane.store.knowledge_version
        result = plane.reconcile()
        assert sorted(result["changed_paths"]) == ["app.py", "readme_notes.md"]
        assert result["knowledge_version"] > version

        after = {
            (s["name"], s["occurrence"]): s
            for s in _entities(plane, type="symbol", file_id=app["id"])
        }
        for key in (("Service", 0), ("helper", 0)):
            assert after[key]["id"] == before[key]["id"]
            assert (after[key]["lifecycle"], after[key]["stale"]) == ("ACTIVE", False)
        assert after[("helper", 0)]["line"] == 4
        for key in (("Service.run", 0), ("helper", 1)):
            assert (
                after[key]["lifecycle"],
                after[key]["stale"],
                after[key]["lifecycle_reason"],
            ) == (
                "HISTORICAL",
                True,
                "symbol absent from observed source",
            )

        renamed = plane.store.get(notes["id"], "entity")
        assert (renamed["source_ref"], renamed["lifecycle"], renamed["stale"]) == (
            "readme_notes.md",
            "ACTIVE",
            False,
        )

        (root / "readme_notes.md").unlink()
        assert plane.reconcile()["changed_paths"] == ["readme_notes.md"]
        gone = plane.store.get(notes["id"], "entity")
        assert (gone["lifecycle"], gone["stale"], gone["lifecycle_reason"]) == (
            "HISTORICAL",
            True,
            "source removed; preserved for history",
        )
        assert plane.reconcile()["changed_paths"] == []


def test_indexing_updates_the_project_and_audits_the_change(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo").resolve()
    adopt(root)
    (root / "extra.py").write_text("value = 1\n")
    with Plane(root) as plane:
        started = time.time()
        plane.reconcile()
        report = scan(root)
        (project,) = plane.store.list("project")
        assert (project["last_fingerprint"], project["last_commit"], project["coverage"]) == (
            report["fingerprint"],
            report["commit"],
            report["coverage"],
        )
        assert started <= project["last_reconcile"] <= time.time()
        event = plane.store.db.execute(
            "SELECT actor, action, payload FROM events WHERE action = 'discovery.index' "
            "ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        assert (event["actor"], event["action"], json.loads(event["payload"])) == (
            "local",
            "discovery.index",
            {"changed_paths": ["extra.py"], "fingerprint": report["fingerprint"]},
        )


# --- verify: evidence records and artifacts -----------------------------------------------


def _claimed(project: Any, seconds: int = 300) -> tuple[str, str, dict[str, Any]]:
    data = contract()
    project.approve_command(data["verification"][0]["command"])
    task = project.create_task(data)["id"]
    project.ready(task)
    session = project.join("worker", ["code", "terminal"])["session"]
    project.claim(task, session, seconds)
    project.checkpoint(task, session, checkpoint())
    return task, session, data["verification"][0]


def test_passing_run_persists_evidence_and_its_redacted_artifact(project: Any) -> None:
    (project.root / "test_app.py").write_text(
        "import app\nprint('password=hunter2 ok')\nassert app.value == 1\n"
    )
    task, session, spec = _claimed(project, seconds=10)
    expected_binding = binding(project, project.store.get(task, "task"))
    started = time.time()

    (record,) = verify(project, task, session)["evidence"]

    artifact = project.directory / "evidence" / f"{record['id']}.json"
    assert record["id"].startswith("EVD-")
    assert record["run_id"].startswith("RUN-")
    assert {
        k: record[k]
        for k in record
        if k not in {"id", "version", "run_id", "started_at", "finished_at"}
    } == {
        "task_id": task,
        "kind": spec["kind"],
        "verifier": digest(spec),
        "acceptance": spec["acceptance"],
        "result": "PASS",
        "exit_code": 0,
        "command": spec["command"],
        "binding": expected_binding,
        "knowledge_version": project.store.knowledge_version,
        "artifact_hash": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "artifact_ref": f".agentic/control/evidence/{record['id']}.json",
        "stale": False,
    }
    assert started <= record["started_at"] <= record["finished_at"] <= time.time()

    output = json.loads(artifact.read_text(encoding="utf-8"))
    # encode() writes canonical JSON, so the keys are stored in sorted order.
    assert list(output) == [
        "command",
        "error",
        "exit_code",
        "finished_at",
        "result",
        "started_at",
        "stderr",
        "stdout",
        "tool",
    ]
    assert (output["tool"], output["command"], output["exit_code"], output["result"]) == (
        spec["command"][0],
        spec["command"],
        0,
        "PASS",
    )
    assert (output["started_at"], output["finished_at"]) == (
        record["started_at"],
        record["finished_at"],
    )
    assert "[REDACTED] ok" in output["stdout"] and "hunter2" not in output["stdout"]
    assert output["error"] == ""

    current = project.store.get(task, "task")
    assert (current["state"], current["active_run"], current["attempts"]) == ("VERIFYING", None, 1)
    assert 0 < current["runtime_used"] < 30
    (lease,) = [item for item in project.store.list("lease") if item["task_id"] == task]
    # The 10-second lease is extended to cover the remaining runtime budget plus 30s.
    assert lease["expires_at"] >= started + 30 - current["runtime_used"] + 29


def test_failing_run_records_the_failure_and_accumulates_runtime(project: Any) -> None:
    task, session, spec = _claimed(project)
    assert verify(project, task, session)["status"] == "PASS"
    first_runtime = project.store.get(task, "task")["runtime_used"]

    (project.root / "app.py").write_text("value = 0\n")
    (record,) = verify(project, task, session)["evidence"]
    output = json.loads((project.directory / "evidence" / f"{record['id']}.json").read_text())

    assert (record["result"], output["result"]) == ("FAIL", "FAIL")
    assert record["exit_code"] == output["exit_code"] != 0
    assert "AssertionError" in output["stderr"]
    current = project.store.get(task, "task")
    assert (current["state"], current["attempts"]) == ("FAILED", 2)
    assert current["runtime_used"] > first_runtime


# --- boundaries found by mutation testing -------------------------------------------------


def test_adoption_works_when_the_payload_directory_already_exists(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo")
    (root / ".agentic").mkdir()
    (root / ".agentic" / "MASTER_PROMPT.md").write_text("# Prompt\n")
    assert adopt(root)["adopted"] is True
    assert (root / ".agentic" / "control" / "state.db").is_file()


def test_reconcile_returns_the_current_coverage(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo").resolve()
    adopt(root)
    (root / "extra.py").write_text("value = 1\n")
    with Plane(root) as plane:
        assert plane.reconcile()["coverage"] == scan(root)["coverage"]


def test_removed_python_file_retires_its_symbols(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo").resolve()
    adopt(root)
    with Plane(root) as plane:
        (app,) = _entities(plane, type="file", source_ref="app.py")
        symbol_ids = [s["id"] for s in _entities(plane, type="symbol", file_id=app["id"])]
        assert len(symbol_ids) == 4
        edge_ids = [
            row["id"]
            for row in plane.store.db.execute(
                "SELECT id FROM edges WHERE source = ? AND relation = 'contains'", (app["id"],)
            )
        ]
        assert len(edge_ids) == 4 and all(i.startswith("EDGE-") for i in edge_ids)

        (root / "app.py").unlink()
        assert plane.reconcile()["changed_paths"] == ["app.py"]
        for identifier in symbol_ids:
            symbol = plane.store.get(identifier, "entity")
            assert (symbol["lifecycle"], symbol["stale"], symbol["lifecycle_reason"]) == (
                "HISTORICAL",
                True,
                "symbol absent from observed source",
            )


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions and symlinks")
def test_evidence_files_are_private_and_symlinked_directories_are_refused(
    project: Any, tmp_path: Path
) -> None:
    task, session, _ = _claimed(project)
    (record,) = verify(project, task, session)["evidence"]
    evidence_dir = project.directory / "evidence"
    artifact = evidence_dir / f"{record['id']}.json"
    assert (evidence_dir.stat().st_mode & 0o777, artifact.stat().st_mode & 0o777) == (0o700, 0o600)

    elsewhere = tmp_path / "elsewhere"
    evidence_dir.rename(elsewhere)
    evidence_dir.symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(ControlError) as caught:
        verify(project, task, session)
    assert (caught.value.code, str(caught.value)) == (
        "INVALID_PATH",
        "Evidence directory must not be a symlink",
    )


def test_verify_reports_its_task_and_failure(project: Any) -> None:
    task, session, _ = _claimed(project)
    (project.root / "app.py").write_text("value = 0\n")
    result = verify(project, task, session)
    assert result == {"task_id": task, "status": "FAIL", "evidence": result["evidence"]}
    assert [e["result"] for e in result["evidence"]] == ["FAIL"]


@pytest.mark.parametrize("already_used", [None, 20.0])
def test_lease_covers_the_remaining_runtime_budget(
    project: Any, already_used: float | None
) -> None:
    task, session, _ = _claimed(project, seconds=10)  # max_runtime is 30
    if already_used is not None:
        _force(project, "task", task, runtime_used=already_used)
    remaining = 30 - (already_used or 0)

    before = time.time()
    (record,) = verify(project, task, session)["evidence"]
    after = time.time()

    (lease,) = [item for item in project.store.list("lease") if item["task_id"] == task]
    assert before + remaining + 30 <= lease["expires_at"] <= after + remaining + 30
    used = project.store.get(task, "task")["runtime_used"] - (already_used or 0)
    assert 0 < used <= record["finished_at"] - record["started_at"] + 0.05


@pytest.mark.parametrize("already_used", [29.0, 29.5])
def test_verifier_timeout_is_the_remaining_budget(project: Any, already_used: float) -> None:
    (project.root / "test_app.py").write_text("import time\ntime.sleep(5)\n")
    task, session, _ = _claimed(project)
    _force(project, "task", task, runtime_used=already_used)

    result = verify(project, task, session)

    assert result["status"] == "FAIL"
    assert [e["result"] for e in result["evidence"]] == ["BLOCKED"]
    assert project.store.get(task, "task")["runtime_used"] < already_used + 3


def test_evidence_is_blocked_when_the_lease_is_revoked_during_the_run(
    project: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agentic_discipline.control import verification

    task, session, _ = _claimed(project)
    real_run_gate = verification.run_gate

    def revoke_after_run(*args: Any, **kwargs: Any) -> Any:
        outcome = real_run_gate(*args, **kwargs)
        (lease,) = [item for item in project.store.list("lease") if item["task_id"] == task]
        _force(project, "lease", lease["id"], state="REVOKED")
        return outcome

    monkeypatch.setattr(verification, "run_gate", revoke_after_run)
    (record,) = verify(project, task, session)["evidence"]
    assert record["result"] == "BLOCKED"


def _actors(project: Any, action: str) -> list[str]:
    rows = project.store.db.execute(
        "SELECT actor FROM events WHERE action = ? ORDER BY seq", (action,)
    )
    return [row["actor"] for row in rows]


def test_verification_writes_are_attributed_to_the_owning_agent(project: Any) -> None:
    data = contract()
    project.approve_command(data["verification"][0]["command"])
    task = project.create_task(data)["id"]
    project.ready(task)
    agent = project.join("worker", ["code", "terminal"])
    project.claim(task, agent["session"])
    project.checkpoint(task, agent["session"], checkpoint())
    before_tasks = len(_actors(project, "task.write"))

    verify(project, task, agent["session"])

    # The RUNNING write, the evidence and the final state all carry the lease owner.
    assert _actors(project, "task.write")[before_tasks:] == [agent["id"], agent["id"]]
    assert _actors(project, "evidence.write") == [agent["id"]]


def test_symbols_of_a_removed_file_become_history(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo").resolve()
    adopt(root)
    (root / "app.py").unlink()

    with Plane(root) as plane:
        plane.reconcile()
        (file_entity,) = _entities(plane, type="file", source_ref="app.py")
        symbols = _entities(plane, type="symbol", file_id=file_entity["id"])

    assert symbols
    assert {s["lifecycle"] for s in symbols} == {"HISTORICAL"}
