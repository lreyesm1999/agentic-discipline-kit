"""Control-plane CLI dispatch, command by command.

Every CLI command is a thin mapping onto a versioned application operation. The
existing workflow test ran the commands and checked that some data came back, so
a command could call the wrong operation, drop an option such as --budget or
--historical, or forget the session without failing. Each case records the exact
operation and payload the command sends.
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from conftest import checkpoint, contract
from test_kernel import entity

from agentic_discipline.control import cli
from agentic_discipline.control.contracts import ControlError

TOKEN = "session-token"
RESULT = {"api_version": "2", "data": {"status": "PASS"}}


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any], bool]]:
    recorded: list[tuple[str, dict[str, Any], bool]] = []

    def fake(plane: Any, operation: str, data: dict[str, Any], local: bool = False) -> Any:
        recorded.append((operation, data, local))
        return RESULT

    monkeypatch.setattr(cli, "call", fake)
    return recorded


@pytest.fixture
def files(project: Any, tmp_path: Path) -> dict[str, Path]:
    session_file = tmp_path / "worker-session.json"
    session_file.write_text(json.dumps({"session": TOKEN}), encoding="utf-8")
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(contract()), encoding="utf-8")
    progress = tmp_path / "checkpoint.json"
    progress.write_text(json.dumps(checkpoint()), encoding="utf-8")
    return {"session": session_file, "plan": plan, "checkpoint": progress}


def _run(project: Any, *arguments: str) -> Any:
    return cli.run(cli.parser().parse_args(["--root", str(project.root), *arguments]))


def _expand(arguments: tuple[str, ...], files: dict[str, Path]) -> list[str]:
    return [str(files[a[1:-1]]) if a.startswith("{") else a for a in arguments]


SESSION = ("--session-file", "{session}")
DISPATCH = [
    (("status",), "status", {}),
    (("doctor",), "doctor", {}),
    (("reconcile",), "reconcile", {}),
    (("api", "task_list"), "task_list", {}),
    (("api", "task_create", "--input", "{plan}"), "task_create", contract()),
    (("api", "claim_task", "--input", "{checkpoint}", *SESSION), "claim_task", None),
    (
        ("agent", "heartbeat", "--task", "TASK-1", *SESSION),
        "heartbeat",
        {"task_id": "TASK-1", "session": TOKEN},
    ),
    (("knowledge", "query", "orders"), "query_knowledge", {"text": "orders", "historical": False}),
    (
        ("knowledge", "query", "orders", "--graph", "code", "--historical"),
        "query_knowledge",
        {"text": "orders", "historical": True, "graph": "code"},
    ),
    (("knowledge", "show", "ENT-1"), "knowledge_show", {"identifier": "ENT-1"}),
    (("knowledge", "history", "ENT-1"), "knowledge_history", {"identifier": "ENT-1"}),
    (("knowledge", "impact", "ENT-1"), "impact_analysis", {"identifier": "ENT-1"}),
    (("plan", "audit", "--input", "{plan}"), "plan_audit", {"plan": contract()}),
    (("readiness", "TASK-1"), "readiness", {"task_id": "TASK-1"}),
    (
        ("context", "audit", "TASK-1", "--budget", "500"),
        "get_context",
        {"task_id": "TASK-1", "budget": 500},
    ),
    (("task", "list"), "task_list", {}),
    (("task", "ready"), "get_ready_tasks", {}),
    (("task", "create", "--input", "{plan}"), "task_create", {"contract": contract()}),
    (("task", "ready", "TASK-1"), "task_ready", {"task_id": "TASK-1"}),
    (("task", "context", "TASK-1"), "get_context", {"task_id": "TASK-1", "budget": 16000}),
    (("task", "claim", "TASK-1", *SESSION), "claim_task", {"task_id": "TASK-1", "session": TOKEN}),
    (
        ("task", "checkpoint", "TASK-1", "--input", "{checkpoint}", *SESSION),
        "checkpoint_task",
        {"task_id": "TASK-1", "session": TOKEN, "data": checkpoint()},
    ),
    (
        ("task", "resume", "TASK-1", "--budget", "900", *SESSION),
        "resume_task",
        {"task_id": "TASK-1", "session": TOKEN, "budget": 900},
    ),
    (
        ("task", "release", "TASK-1", *SESSION),
        "release_task",
        {"task_id": "TASK-1", "session": TOKEN},
    ),
    (
        ("task", "block", "TASK-1", "--reason", "Need a decision", *SESSION),
        "release_task",
        {"task_id": "TASK-1", "session": TOKEN, "blocker": "Need a decision"},
    ),
    (
        ("task", "verify", "TASK-1", *SESSION),
        "record_evidence",
        {"task_id": "TASK-1", "session": TOKEN},
    ),
    (
        ("task", "complete", "TASK-1", *SESSION),
        "complete_task",
        {"task_id": "TASK-1", "session": TOKEN},
    ),
    (
        ("task", "heartbeat", "TASK-1", *SESSION),
        "heartbeat",
        {"task_id": "TASK-1", "session": TOKEN},
    ),
]


@pytest.mark.parametrize(
    ("arguments", "operation", "payload"), DISPATCH, ids=[" ".join(d[0]) for d in DISPATCH]
)
def test_command_calls_its_operation_with_its_payload(
    project: Any,
    calls: list[Any],
    files: dict[str, Path],
    arguments: tuple[str, ...],
    operation: str,
    payload: dict[str, Any] | None,
) -> None:
    if payload is None:
        payload = {**checkpoint(), "session": TOKEN}
    assert _run(project, *_expand(arguments, files)) is RESULT
    assert calls == [(operation, payload, True)]


def test_status_summaries_come_from_the_status_operation(
    project: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded: list[Any] = []
    status = {"project": {"coverage": {"files": 3}}, "evidence": {"current": 1}}

    def fake(plane: Any, operation: str, data: dict[str, Any], local: bool = False) -> Any:
        recorded.append((operation, data, local))
        return {"data": status}

    monkeypatch.setattr(cli, "call", fake)
    # Evolution lists retired knowledge too, so give it something only history shows.
    (old,) = project.knowledge.apply([entity("old")], project.store.knowledge_version, "setup")[
        "entities"
    ]
    project.knowledge.lifecycle(old["id"], "RETIRED", "gone")
    assert project.knowledge.query(historical=True) != project.knowledge.query()
    assert _run(project, "discovery") == {"data": {"files": 3}}
    assert _run(project, "evidence", "list") == {"data": {"current": 1}}
    assert _run(project, "evolution") == {"data": project.knowledge.query(historical=True)}
    assert recorded == [("status", {}, True)] * 3


def test_agent_status_lists_the_agents(project: Any) -> None:
    project.join("worker", ["code"])
    assert _run(project, "agent", "status") == {"data": project.status()["agents"]}


@pytest.mark.parametrize("dry_run", [False, True])
def test_adopt_does_not_open_a_plane(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dry_run: bool
) -> None:
    monkeypatch.setattr(cli, "adopt", lambda path, dry: {"path": path, "dry_run": dry})
    missing = tmp_path / "not-a-project"
    arguments = ["--root", str(missing), "adopt", str(tmp_path)] + (
        ["--dry-run"] if dry_run else []
    )
    assert cli.run(cli.parser().parse_args(arguments)) == {
        "api_version": "2",
        "data": {"path": tmp_path, "dry_run": dry_run},
    }
    assert not missing.exists()


def test_backup_reports_its_file_and_the_audit(project: Any, tmp_path: Path) -> None:
    target = tmp_path / "copy.sqlite"
    assert _run(project, "backup", str(target)) == {
        "data": {"backup": str(target), "audit": project.store.audit()}
    }
    assert target.is_file()


@pytest.mark.parametrize("dry_run", [False, True])
def test_migrate_and_rollback_pass_their_options(
    project: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dry_run: bool
) -> None:
    seen: list[Any] = []
    monkeypatch.setattr(
        cli, "import_legacy", lambda plane, path, dry: seen.append((plane.root, path, dry)) or "M"
    )
    monkeypatch.setattr(
        cli,
        "rollback_changeset",
        lambda plane, identifier, reason: seen.append((plane.root, identifier, reason)) or "R",
    )
    legacy = tmp_path / "legacy.json"

    flags = ["--dry-run"] if dry_run else []
    assert _run(project, "migrate", "--input", str(legacy), *flags) == {"data": "M"}
    assert _run(project, "rollback", "CHAN-1", "--reason", "undo") == {"data": "R"}
    assert seen == [
        (project.root, legacy, dry_run),
        (project.root, "CHAN-1", "undo"),
    ]


def test_mcp_serves_standard_streams(project: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from agentic_discipline.control import mcp

    seen: list[Any] = []
    monkeypatch.setattr(
        mcp, "serve", lambda plane, source, sink: seen.append((plane.root, source, sink))
    )
    assert _run(project, "mcp") is None
    assert seen == [(project.root, sys.stdin, sys.stdout)]


def test_console_serves_on_the_requested_port(
    project: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from agentic_discipline.control import console

    seen: list[Any] = []

    class Web:
        server_port = 43210

        def serve_forever(self) -> None:
            seen.append("served")

    @contextmanager
    def server(root: Path, port: int) -> Any:
        seen.append((root, port))
        yield Web()

    monkeypatch.setattr(console, "server", server)
    assert _run(project, "console", "--port", "9001") is None
    assert seen == [(project.root, 9001), "served"]
    assert capsys.readouterr().err == "Project console: http://127.0.0.1:43210\n"


# --- agent join -----------------------------------------------------------------------------


def test_join_writes_a_private_session_file_and_returns_no_secret(
    project: Any, tmp_path: Path
) -> None:
    session_file = project.root.parent / (project.root.name + "-builder.json")

    result = _run(
        project,
        "agent",
        "join",
        "--name",
        "builder",
        "--capabilities",
        "code,database",
        "--session-file",
        str(session_file),
    )

    saved = json.loads(session_file.read_text(encoding="utf-8"))
    assert set(saved) == {"id", "name", "session"}
    assert result == {
        "data": {"id": saved["id"], "name": "builder", "session_file": str(session_file)}
    }
    agent = project.authenticate(saved["session"])
    assert (agent["id"], agent["name"], agent["capabilities"]) == (
        saved["id"],
        "builder",
        ["code", "database"],
    )
    if os.name == "posix":
        assert session_file.stat().st_mode & 0o777 == 0o600


def test_join_uses_worker_defaults(project: Any, tmp_path: Path) -> None:
    session_file = project.root.parent / (project.root.name + "-worker.json")
    _run(project, "agent", "join", "--session-file", str(session_file))
    agent = project.authenticate(json.loads(session_file.read_text(encoding="utf-8"))["session"])
    assert (agent["name"], agent["capabilities"]) == ("worker", ["code", "terminal"])


@pytest.mark.parametrize(
    ("where", "code", "message"),
    [
        (None, "SESSION_DESTINATION", "Choose a new --session-file outside the repository"),
        ("existing", "SESSION_DESTINATION", "Choose a new --session-file outside the repository"),
        ("repository", "SECRET_PATH", "Keep agent sessions outside the repository"),
    ],
)
def test_join_refuses_unsafe_session_destinations(
    project: Any, tmp_path: Path, where: str | None, code: str, message: str
) -> None:
    arguments = ["agent", "join"]
    if where == "existing":
        existing = tmp_path / "existing.json"
        existing.write_text("{}", encoding="utf-8")
        arguments += ["--session-file", str(existing)]
    elif where == "repository":
        arguments += ["--session-file", str(project.root / "session.json")]
    agents = project.store.list("agent")

    with pytest.raises(ControlError) as caught:
        _run(project, *arguments)

    assert (caught.value.code, str(caught.value)) == (code, message)
    assert project.store.list("agent") == agents
    assert not (project.root / "session.json").exists()


# --- input helpers --------------------------------------------------------------------------


def test_input_files_are_bounded_json_objects(tmp_path: Path) -> None:
    assert cli.read_input(None) == {}
    limit = tmp_path / "limit.json"
    limit.write_text('{"x": "' + "a" * (1048576 - 9) + '"}', encoding="utf-8")
    assert limit.stat().st_size == 1048576
    assert set(cli.read_input(limit)) == {"x"}

    for content, code, message in (
        ('{"x": "' + "a" * (1048576 - 8) + '"}', "INPUT_TOO_LARGE", "JSON input exceeds 1 MiB"),
        ("[1, 2]", "INVALID_INPUT", "JSON input must be an object"),
    ):
        path = tmp_path / "input.json"
        path.write_text(content, encoding="utf-8")
        with pytest.raises(ControlError) as caught:
            cli.read_input(path)
        assert (caught.value.code, str(caught.value)) == (code, message)


def test_session_files_must_be_regular_files(tmp_path: Path) -> None:
    regular = tmp_path / "session.json"
    regular.write_text(json.dumps({"session": 123}), encoding="utf-8")
    assert cli.session(regular) == "123"

    candidates: list[Path | None] = [None, tmp_path / "missing.json", tmp_path]
    if os.name == "posix":
        link = tmp_path / "link.json"
        link.symlink_to(regular)
        candidates.append(link)
    for candidate in candidates:
        with pytest.raises(ControlError) as caught:
            cli.session(candidate)
        assert (caught.value.code, str(caught.value)) == (
            "SESSION_REQUIRED",
            "Supply --session-file created by agent join",
        )


def test_the_control_command_reports_the_package_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from agentic_discipline import __version__
    from agentic_discipline.control.cli import parser

    with pytest.raises(SystemExit) as caught:
        parser().parse_args(["--version"])
    assert caught.value.code == 0
    assert capsys.readouterr().out == __version__ + "\n"
