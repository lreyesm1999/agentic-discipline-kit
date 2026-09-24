import io
import json
import sys
import threading
from http.client import HTTPConnection
from pathlib import Path

import pytest
from conftest import checkpoint, contract
from test_execution import setup_task

from agentic_discipline.control import cli
from agentic_discipline.control.api import call
from agentic_discipline.control.console import server
from agentic_discipline.control.contracts import ControlError
from agentic_discipline.control.mcp import MAX_MESSAGE, Session, serve
from agentic_discipline.control.migration import import_legacy


def test_api_discovery_and_contracts(project):
    for name in (
        "status",
        "knowledge_health",
        "discover_project",
        "reconcile",
        "task_list",
        "get_ready_tasks",
        "timeline",
    ):
        assert call(project, name, {})["api_version"] == "2"
    with pytest.raises(ControlError):
        call(project, "unknown", {})
    with pytest.raises(ControlError):
        call(project, "status", {"extra": True})
    with pytest.raises(ControlError):
        call(project, "approve_command", {"command": ["anything"]})
    node = project.knowledge.query()[0]
    for name in ("knowledge_show", "knowledge_history", "impact_analysis"):
        assert call(project, name, {"identifier": node["id"]})["data"] is not None
    assert call(project, "query_knowledge", {"text": "value", "graph": "code"})["data"]
    task, token = setup_task(project)
    for name in ("readiness", "get_context"):
        assert call(project, name, {"task_id": task})["data"]
    assert call(project, "plan_audit", {"plan": contract()})["data"]["status"] == "READY"
    assert (
        call(project, "heartbeat", {"task_id": task, "session": token})["data"]["state"] == "ACTIVE"
    )
    call(project, "checkpoint_task", {"task_id": task, "session": token, "data": checkpoint()})
    call(project, "resume_task", {"task_id": task, "session": token})
    assert (
        call(project, "record_evidence", {"task_id": task, "session": token})["data"]["status"]
        == "PASS"
    )
    assert (
        call(project, "complete_task", {"task_id": task, "session": token})["data"]["state"]
        == "COMPLETED"
    )


def test_mcp_protocol_initialization_permissions_and_json_errors(project):
    s = Session(project)

    def request(method, params=None):
        return {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params if params is not None else {},
        }

    assert s.receive([])["error"]["code"] == -32600
    assert s.receive({**request("ping"), "id": []})["error"]
    assert s.receive(request("ping", []))["error"]
    assert s.receive(request("ping"))["result"] == {}
    assert s.receive(request("tools/list"))["error"]
    assert s.receive(request("initialize"))["error"]
    init = request(
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1"},
        },
    )
    assert s.receive(init)["result"]["capabilities"]["tools"]
    assert s.receive(init)["error"]
    assert s.receive({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert s.receive(request("unknown"))["error"]["code"] == -32601
    names = {t["name"] for t in s.receive(request("tools/list"))["result"]["tools"]}
    assert "claim_task" in names and "approve_command" not in names
    assert s.receive(request("tools/call", {"name": "approve_command"}))["error"]
    assert s.receive(request("tools/call", {"name": "status"}))["result"]["isError"] is False
    assert s.receive(request("tools/call", {"name": "claim_task", "arguments": {}}))["result"][
        "isError"
    ]
    output = io.StringIO()
    serve(
        project,
        io.StringIO(
            "bad json\n" + "x" * (MAX_MESSAGE + 1) + "\n" + json.dumps(request("ping")) + "\n"
        ),
        output,
    )
    responses = [json.loads(line) for line in output.getvalue().splitlines()]
    assert [r.get("error", {}).get("code") for r in responses] == [-32700, -32600, None]


def test_console_real_http_and_host_boundary(project):
    http = server(project.root, 0)
    worker = threading.Thread(target=http.serve_forever, daemon=True)
    worker.start()

    def fetch(method, path, headers=None, body=None):
        # The handler speaks HTTP/1.0 and closes each response, so no connection is reused.
        connection = HTTPConnection("127.0.0.1", http.server_port)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, response.read(), response.headers
        finally:
            connection.close()

    try:
        for path in ("/", "/app.js", "/app.css", "/api/status", "/api/timeline"):
            status, body, headers = fetch("GET", path)
            assert status == 200 and body
            assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
            if path == "/api/status":
                assert json.loads(body)["data"]["project"]["name"] == project.root.name
        assert fetch("GET", "/missing")[0] == 404
        assert fetch("GET", "/", headers={"Host": "attacker.example"})[0] == 403
        assert fetch("POST", "/api/status", body="{}")[0] == 501
    finally:
        http.shutdown()
        http.server_close()
        worker.join()


def test_legacy_import_is_explicit_idempotent_historical_and_reversible(project, tmp_path: Path):
    graph = {
        "feature_id": "old",
        "nodes": [{"id": "REQ-1", "type": "requirement"}, {"id": "TEST-1", "type": "test"}],
        "edges": [{"from": "REQ-1", "to": "TEST-1", "relation": "verified_by"}],
    }
    path = project.root / "legacy.json"
    path.write_text(json.dumps(graph))
    original = path.read_bytes()
    before = len(project.store.list("entity"))
    assert import_legacy(project, path, True)["dry_run"]
    assert len(project.store.list("entity")) == before
    imported = import_legacy(project, path)
    assert import_legacy(project, path)["already_imported"]
    assert path.read_bytes() == original
    assert project.store.get(imported["mapping"]["REQ-1"])["lifecycle"] == "HISTORICAL"
    backup = project.root / "backup.sqlite"
    project.store.backup(backup)
    assert backup.is_file()
    with pytest.raises(ControlError):
        project.store.backup(backup)


def test_cli_human_and_json_workflows(project, tmp_path: Path, monkeypatch, capsys):
    root = project.root

    def run(arguments):
        return cli.run(cli.parser().parse_args(["--root", str(root), *arguments]))

    for command in (
        ["status"],
        ["doctor"],
        ["reconcile"],
        ["agent", "status"],
        ["discovery", "status"],
        ["evidence", "list"],
        ["evolution", "status"],
        ["task", "list"],
        ["task", "ready"],
        ["knowledge", "query", "value"],
    ):
        assert run(command)["data"] is not None
    plan = root / "task.json"
    plan.write_text(json.dumps(contract()))
    assert run(["plan", "audit", "--input", str(plan)])["data"]["status"] == "READY"
    task = run(["task", "create", "--input", str(plan)])["data"]["id"]
    command_file = root / "command.json"
    command_file.write_text(json.dumps({"command": contract()["verification"][0]["command"]}))
    run(["api", "approve_command", "--input", str(command_file)])
    run(["task", "ready", task])
    session_file = root.parent / (root.name + "-worker.json")
    worker = run(["agent", "join", "--session-file", str(session_file)])
    assert "session" not in worker["data"]
    args = ["--session-file", str(session_file)]
    run(["task", "claim", task, *args])
    run(["agent", "heartbeat", "--task", task, *args])
    run(["context", "audit", task])
    run(["readiness", task])
    cp = root / "checkpoint.json"
    cp.write_text(json.dumps(checkpoint()))
    run(["task", "checkpoint", task, "--input", str(cp), *args])
    run(["task", "resume", task, *args])
    run(["task", "release", task, *args])
    node = project.knowledge.query()[0]["id"]
    for action in ("show", "history", "impact"):
        run(["knowledge", action, node])
    monkeypatch.setattr(sys, "argv", ["agentic", "--root", str(root), "status", "--json"])
    cli.main()
    assert json.loads(capsys.readouterr().out)["api_version"] == "2"
    monkeypatch.setattr(sys, "argv", ["agentic", "--root", str(root), "status"])
    cli.main()
    assert "Knowledge revision:" in capsys.readouterr().out
    monkeypatch.setattr(sys, "argv", ["agentic", "--root", str(root), "api", "claim_task"])
    with pytest.raises(SystemExit) as raised:
        cli.main()
    assert raised.value.code == 2 and json.loads(capsys.readouterr().out)["status"] == "ERROR"
