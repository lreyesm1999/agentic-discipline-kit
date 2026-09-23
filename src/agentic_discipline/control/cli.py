"""Human CLI with JSON parity and generic access to versioned application commands."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, cast

from .. import __version__
from . import API_VERSION
from .api import SCHEMAS, call
from .contracts import ControlError, encode, require
from .migration import import_legacy, rollback_changeset
from .plane import Plane, adopt


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="agentic", description="Agentic Discipline 2 local control plane"
    )
    root.add_argument("--version", action="version", version=__version__)
    root.add_argument("--root", type=Path, default=Path.cwd())
    commands = root.add_subparsers(dest="group", required=True)
    adoption = commands.add_parser("adopt")
    adoption.add_argument("path", type=Path, nargs="?", default=Path.cwd())
    adoption.add_argument("--dry-run", action="store_true")
    for name in ("status", "doctor", "reconcile"):
        commands.add_parser(name)
    api = commands.add_parser("api", help="Call a versioned operation using a JSON input file")
    api.add_argument("operation", choices=sorted(SCHEMAS))
    api.add_argument("--input", type=Path)
    api.add_argument("--session-file", type=Path)
    task = commands.add_parser("task")
    task.add_argument(
        "action",
        choices=[
            "list",
            "ready",
            "create",
            "claim",
            "context",
            "checkpoint",
            "resume",
            "release",
            "block",
            "verify",
            "complete",
            "heartbeat",
        ],
    )
    task.add_argument("identifier", nargs="?")
    task.add_argument("--input", type=Path)
    task.add_argument("--session-file", type=Path)
    task.add_argument("--reason")
    task.add_argument("--budget", type=int, default=16000)
    agent = commands.add_parser("agent")
    agent.add_argument("action", choices=["join", "status", "heartbeat"])
    agent.add_argument("--name", default="worker")
    agent.add_argument("--capabilities", default="code,terminal")
    agent.add_argument("--session-file", type=Path)
    agent.add_argument("--task")
    knowledge = commands.add_parser("knowledge")
    knowledge.add_argument("action", choices=["query", "show", "history", "impact"])
    knowledge.add_argument("value", nargs="?", default="")
    knowledge.add_argument("--graph")
    knowledge.add_argument("--historical", action="store_true")
    for name in ("discovery", "evidence", "evolution"):
        command = commands.add_parser(name)
        command.add_argument("action", choices=["status", "list"], nargs="?", default="status")
    plan = commands.add_parser("plan")
    plan.add_argument("action", choices=["audit"])
    plan.add_argument("--input", required=True, type=Path)
    assurance = commands.add_parser(
        "assurance", help="Proof obligations, their current evidence and remaining proof debt"
    )
    assurance.add_argument(
        "action",
        choices=[
            "plan",
            "verify",
            "status",
            "explain",
            "debt",
            "registry",
            "integrity",
            "waive",
            "resolve",
            "migrate",
            "rollback",
        ],
    )
    assurance.add_argument("identifier", nargs="?")
    assurance.add_argument("--session-file", type=Path)
    assurance.add_argument("--input", type=Path)
    assurance.add_argument("--reason")
    assurance.add_argument("--authorization")
    assurance.add_argument("--decision")
    assurance.add_argument("--rejected", action="store_true")
    assurance.add_argument("--compile", action="store_true")
    assurance.add_argument("--dry-run", action="store_true")
    readiness = commands.add_parser("readiness")
    readiness.add_argument("identifier")
    context = commands.add_parser("context")
    context.add_argument("action", choices=["audit"])
    context.add_argument("identifier")
    context.add_argument("--budget", type=int, default=16000)
    commands.add_parser("mcp")
    console = commands.add_parser("console")
    console.add_argument("--port", type=int, default=8765)
    migrate = commands.add_parser("migrate")
    migrate.add_argument("--input", type=Path, required=True)
    migrate.add_argument("--dry-run", action="store_true")
    backup = commands.add_parser("backup")
    backup.add_argument("path", type=Path)
    rollback = commands.add_parser("rollback")
    rollback.add_argument("identifier")
    rollback.add_argument("--reason", required=True)
    # Each subcommand accepts --json in the conventional trailing position.
    for subparser in commands.choices.values():
        subparser.add_argument("--json", action="store_true")
    return root


def read_input(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    require(path.stat().st_size <= 1048576, "INPUT_TOO_LARGE", "JSON input exceeds 1 MiB")
    data = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(data, dict), "INVALID_INPUT", "JSON input must be an object")
    return cast(dict[str, Any], data)


def session(path: Path | None) -> str:
    require(
        path is not None and path.is_file() and not path.is_symlink(),
        "SESSION_REQUIRED",
        "Supply --session-file created by agent join",
    )
    return str(read_input(path)["session"])


def render_assurance(action: str, data: dict[str, Any]) -> str:
    """The plain reading of an assurance answer; --json carries the whole record."""
    lines: list[str] = []
    if action == "explain" and "headline" in data:
        lines = [data["headline"], f"{data['required']} mandatory proof obligations."]
        lines += [f"  {state:<16} {count}" for state, count in sorted(data["counts"].items())]
        for item in data["outstanding"]:
            lines += [
                "",
                f"{item['status']}:",
                f"  {item['obligation_id']}",
                f"  {item['claim']}",
                f"  Reason: {item['reason']}",
            ]
            for identifier in item["current_evidence"] + item["stale_evidence"]:
                lines.append(f"  Evidence: {identifier}")
        if data["required_next_actions"]:
            lines.append("")
            lines.append("Required next actions:")
            lines += [
                f"  {number}. {action_text}"
                for number, action_text in enumerate(data["required_next_actions"], 1)
            ]
        return "\n".join(lines)
    if action == "explain":
        evidence = [
            f"  {e['id']} {e['result']} {e['currency']} ({e['kind']}, {e['evidence_class']})"
            for e in data["evidence"]
        ]
        lines = [
            data["obligation"]["id"],
            "Claim:",
            f"  {data['claim']}",
            "Origin:",
            f"  {data['required_because']}",
            "Affected by:",
            *(f"  {p}" for p in data["affected_paths"] or ["(declared task scope)"]),
            "Evidence:",
            *(evidence or ["  none recorded"]),
            "Current state:",
            f"  {data['status']} - {data['reason']}",
        ]
        if data["human_request"]:
            lines += ["Human resolution:", f"  {data['human_request']['resolve_with']}"]
        return "\n".join(lines)
    for report in data["tasks"]:
        identifier = report["task_id"]
        counts = report["counts"]
        lines.append(f"{identifier} ASSURANCE")
        lines.append(f"  Required obligations {report['required']}")
        for state, count in sorted(counts.items()):
            lines.append(f"  {state:<22} {count}")
        lines.append(f"  Proof debt           {report['proof_debt']}")
        if action == "status":
            lines.append(f"  Decision             {report['decision']['decision']}")
        for item in report.get("outstanding", []):
            lines.append(f"  - {item['obligation_id']} {item['status']}: {item['claim']}")
    if not lines:
        lines.append("No assurance plan has been compiled yet")
    return "\n".join(lines)


def assurance_command(plane: Plane, args: argparse.Namespace) -> dict[str, Any]:
    if args.action == "plan":
        if args.compile:
            return call(plane, "assurance_compile", {"task_id": args.identifier}, local=True)
        return call(plane, "assurance_plan", {"task_id": args.identifier})
    if args.action == "verify":
        return call(
            plane,
            "assurance_verify",
            {"task_id": args.identifier, "session": session(args.session_file)},
        )
    if args.action in {"status", "debt"}:
        data = {"task_id": args.identifier} if args.identifier else {}
        return call(plane, "assurance_" + args.action, data)
    if args.action == "explain":
        return call(plane, "assurance_explain", {"obligation_id": args.identifier})
    if args.action in {"registry", "integrity"}:
        return call(plane, "assurance_" + args.action, {})
    if args.action == "waive":
        require(
            args.reason is not None and args.authorization is not None,
            "DECISION_REQUIRED",
            "A waiver needs --reason and --authorization",
        )
        return call(
            plane,
            "assurance_waive",
            {
                "obligation_id": args.identifier,
                "reason": args.reason,
                "authorization": args.authorization,
            },
            local=True,
        )
    if args.action == "resolve":
        require(args.decision is not None, "DECISION_REQUIRED", "Record --decision")
        return call(
            plane,
            "assurance_resolve_human",
            {
                "obligation_id": args.identifier,
                "decision": args.decision,
                "accepted": not args.rejected,
            },
            local=True,
        )
    if args.action == "migrate":
        return call(plane, "assurance_migrate", {"dry_run": args.dry_run}, local=True)
    require(args.reason is not None, "REASON_REQUIRED", "Rollback requires --reason")
    return call(
        plane,
        "assurance_rollback",
        {"identifier": args.identifier, "reason": args.reason},
        local=True,
    )


def run(args: argparse.Namespace) -> dict[str, Any] | None:
    if args.group == "adopt":
        return {"api_version": API_VERSION, "data": adopt(args.path, args.dry_run)}
    with Plane(args.root) as plane:
        if args.group == "mcp":
            from .mcp import serve

            serve(plane, sys.stdin, sys.stdout)
            return None
        if args.group == "console":
            from .console import server

            with server(plane.root, args.port) as web:
                print(f"Project console: http://127.0.0.1:{web.server_port}", file=sys.stderr)
                web.serve_forever()
            return None
        if args.group == "backup":
            plane.store.backup(args.path)
            return {"data": {"backup": str(args.path), "audit": plane.store.audit()}}
        if args.group == "migrate":
            return {"data": import_legacy(plane, args.input, args.dry_run)}
        if args.group == "rollback":
            return {"data": rollback_changeset(plane, args.identifier, args.reason)}
        if args.group in {"status", "doctor", "reconcile"}:
            return call(plane, args.group, {}, local=True)
        if args.group == "api":
            data = read_input(args.input)
            if args.session_file:
                data["session"] = session(args.session_file)
            return call(plane, args.operation, data, local=True)
        if args.group == "agent":
            if args.action == "status":
                return {"data": plane.status()["agents"]}
            if args.action == "heartbeat":
                return call(
                    plane,
                    "heartbeat",
                    {"task_id": args.task, "session": session(args.session_file)},
                    local=True,
                )
            require(
                args.session_file is not None and not args.session_file.exists(),
                "SESSION_DESTINATION",
                "Choose a new --session-file outside the repository",
            )
            require(
                not args.session_file.resolve().is_relative_to(plane.root),
                "SECRET_PATH",
                "Keep agent sessions outside the repository",
            )
            joined = plane.join(args.name, args.capabilities.split(","))
            descriptor = os.open(args.session_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, "w") as handle:
                handle.write(encode(joined))
            return {
                "data": {
                    "id": joined["id"],
                    "name": joined["name"],
                    "session_file": str(args.session_file),
                }
            }
        if args.group == "knowledge":
            if args.action == "query":
                data = {"text": args.value, "historical": args.historical}
                if args.graph:
                    data["graph"] = args.graph
                return call(plane, "query_knowledge", data, local=True)
            return call(
                plane,
                {
                    "show": "knowledge_show",
                    "history": "knowledge_history",
                    "impact": "impact_analysis",
                }[args.action],
                {"identifier": args.value},
                local=True,
            )
        if args.group == "assurance":
            return assurance_command(plane, args)
        if args.group == "plan":
            return call(plane, "plan_audit", {"plan": read_input(args.input)}, local=True)
        if args.group in {"readiness", "context"}:
            data = {"task_id": args.identifier}
            if args.group == "context":
                data["budget"] = args.budget
            return call(
                plane, "readiness" if args.group == "readiness" else "get_context", data, local=True
            )
        if args.group in {"discovery", "evidence", "evolution"}:
            status = call(plane, "status", {}, local=True)["data"]
            return {
                "data": status["project"]["coverage"]
                if args.group == "discovery"
                else status["evidence"]
                if args.group == "evidence"
                else plane.knowledge.query(historical=True)
            }
        if args.action == "list" or (args.action == "ready" and args.identifier is None):
            return call(
                plane, "task_list" if args.action == "list" else "get_ready_tasks", {}, local=True
            )
        if args.action == "create":
            return call(plane, "task_create", {"contract": read_input(args.input)}, local=True)
        operations = {
            "ready": "task_ready",
            "claim": "claim_task",
            "context": "get_context",
            "checkpoint": "checkpoint_task",
            "resume": "resume_task",
            "release": "release_task",
            "block": "release_task",
            "verify": "record_evidence",
            "complete": "complete_task",
            "heartbeat": "heartbeat",
        }
        data = {"task_id": args.identifier}
        if args.action not in {"ready", "context"}:
            data["session"] = session(args.session_file)
        if args.action == "checkpoint":
            data["data"] = read_input(args.input)
        if args.action == "block":
            data["blocker"] = args.reason
        if args.action in {"context", "resume"}:
            data["budget"] = args.budget
        return call(plane, operations[args.action], data, local=True)


def main() -> None:
    args = parser().parse_args()
    try:
        result = run(args)
        if result is not None:
            if args.json:
                print(encode(result))
            elif args.group == "assurance" and args.action in {"status", "debt", "explain"}:
                print(render_assurance(args.action, result["data"]))
            elif args.group == "status":
                data = result["data"]
                print(
                    f"Project: {data['project']['name']}\nKnowledge revision: {data['knowledge_version']}"
                )
                for state, count in data["task_counts"].items():
                    print(f"{state}: {count}")
                print(
                    f"Stale knowledge: {data['knowledge']['stale']}\nAudit: {data['audit']['status']}"
                )
            else:
                print(json.dumps(result, indent=2))
            data = result.get("data")
            outcome = data.get("status") if isinstance(data, dict) else None
            if outcome in {"FAIL", "BLOCKED", "ERROR"}:
                raise SystemExit(1 if outcome == "FAIL" else 2)
    except (ControlError, OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        print(
            encode(
                {
                    "api_version": API_VERSION,
                    "status": "ERROR",
                    "code": getattr(exc, "code", "OPERATION_FAILED"),
                    "message": str(exc),
                }
            )
        )
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
