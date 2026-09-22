"""Versioned transport-neutral commands; local authority is not exposed to workers."""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

from . import API_VERSION, preflight
from .assurance import migration as assurance_migration
from .assurance import service as assurance_service
from .contracts import ControlError, require
from .diagnostics import doctor
from .plane import Plane
from .verification import complete, invalidate, verify
from .workspaces import (
    cleanup,
    create_workspace,
    integration_gate,
    merge_workspace,
    parallel_safety,
    refresh_workspace,
)

STRING = {"type": "string", "minLength": 1}
OBJECT = {"type": "object"}
INTEGER = {"type": "integer", "minimum": 1}


def schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required if required is not None else list(properties),
        "additionalProperties": False,
    }


SCHEMAS: dict[str, dict[str, Any]] = {
    "status": schema({}),
    "doctor": schema({}),
    # Both flags default to the safe reading: repair what can be repaired, and look at the
    # working tree. A caller that only wants the report says so.
    "preflight": schema(
        {"repair": {"type": "boolean"}, "deep": {"type": "boolean"}},
        required=[],
    ),
    "discover_project": schema({}),
    "query_knowledge": schema(
        {
            "text": {"type": "string"},
            "graph": STRING,
            "historical": {"type": "boolean"},
            "limit": INTEGER,
            "at_version": {"type": "integer", "minimum": 0},
        },
        [],
    ),
    "knowledge_show": schema({"identifier": STRING}),
    "knowledge_history": schema({"identifier": STRING}),
    "impact_analysis": schema({"identifier": STRING}),
    "get_context": schema({"task_id": STRING, "budget": INTEGER}, ["task_id"]),
    "get_ready_tasks": schema({}),
    "task_list": schema({}),
    "agent_join": schema(
        {"name": STRING, "capabilities": {"type": "array", "items": STRING, "minItems": 1}}
    ),
    "claim_task": schema(
        {"task_id": STRING, "session": STRING, "seconds": INTEGER}, ["task_id", "session"]
    ),
    "heartbeat": schema(
        {"task_id": STRING, "session": STRING, "seconds": INTEGER}, ["task_id", "session"]
    ),
    "checkpoint_task": schema({"task_id": STRING, "session": STRING, "data": OBJECT}),
    "release_task": schema(
        {"task_id": STRING, "session": STRING, "blocker": STRING}, ["task_id", "session"]
    ),
    "resume_task": schema(
        {"task_id": STRING, "session": STRING, "budget": INTEGER}, ["task_id", "session"]
    ),
    "record_evidence": schema({"task_id": STRING, "session": STRING}),
    "complete_task": schema({"task_id": STRING, "session": STRING}),
    "integration_gate": schema({"task_id": STRING, "session": STRING}),
    "reconcile": schema({}),
    "knowledge_health": schema({}),
    "timeline": schema({"identifier": STRING, "limit": INTEGER}, []),
    "readiness": schema({"task_id": STRING}),
    "plan_audit": schema({"plan": OBJECT}),
    "task_create": schema({"contract": OBJECT}),
    "task_ready": schema({"task_id": STRING}),
    "resolve_blocker": schema({"task_id": STRING, "decision": STRING}),
    "task_transition": schema({"task_id": STRING, "state": STRING, "reason": STRING}),
    "resolve_claim": schema({"identifier": STRING, "reason": STRING}),
    "knowledge_apply": schema(
        {
            "changes": {"type": "array", "items": OBJECT, "minItems": 1},
            "base_version": {"type": "integer", "minimum": 0},
            "reason": STRING,
        }
    ),
    "knowledge_link": schema({"source": STRING, "target": STRING, "relation": STRING}),
    "record_discovery": schema({"data": OBJECT}),
    "lifecycle": schema({"identifier": STRING, "state": STRING, "reason": STRING}),
    "approve_command": schema({"command": {"type": "array", "items": STRING, "minItems": 1}}),
    "workspace_refresh": schema({"task_id": STRING}),
    "workspace_merge": schema({"task_id": STRING, "session": STRING}),
    "workspace_create": schema({"task_id": STRING}),
    "workspace_cleanup": schema({"task_id": STRING}),
    "parallel_safety": schema({"left": STRING, "right": STRING}),
    "assurance_status": schema({"task_id": STRING}, []),
    "assurance_plan": schema({"task_id": STRING}),
    "assurance_explain": schema({"obligation_id": STRING}),
    "assurance_debt": schema({"task_id": STRING}, []),
    "assurance_registry": schema({}),
    "assurance_integrity": schema({}),
    "assurance_verify": schema({"task_id": STRING, "session": STRING}),
    "assurance_compile": schema(
        {"task_id": STRING, "phase": {"enum": ["INITIAL", "RECONCILED"]}}, ["task_id"]
    ),
    "assurance_waive": schema({"obligation_id": STRING, "reason": STRING, "authorization": STRING}),
    "assurance_resolve_human": schema(
        {"obligation_id": STRING, "decision": STRING, "accepted": {"type": "boolean"}},
        ["obligation_id", "decision"],
    ),
    "assurance_register_verifier": schema({"descriptor": OBJECT}),
    "assurance_migrate": schema({"dry_run": {"type": "boolean"}}, []),
    "assurance_rollback": schema({"identifier": STRING, "reason": STRING}),
}
LOCAL_ONLY = {
    "task_create",
    "task_ready",
    "resolve_blocker",
    "task_transition",
    "resolve_claim",
    "knowledge_apply",
    "knowledge_link",
    "lifecycle",
    "approve_command",
    "workspace_create",
    "workspace_cleanup",
    "workspace_refresh",
    "workspace_merge",
    "assurance_compile",
    "assurance_waive",
    "assurance_resolve_human",
    "assurance_register_verifier",
    "assurance_migrate",
    "assurance_rollback",
    # Preflight repairs what it safely can, which is a write, so it stays with the owner.
    "preflight",
}
READ_ONLY = {
    "doctor",
    "status",
    "query_knowledge",
    "knowledge_show",
    "knowledge_history",
    "impact_analysis",
    "get_context",
    "get_ready_tasks",
    "task_list",
    "knowledge_health",
    "timeline",
    "readiness",
    "plan_audit",
    "parallel_safety",
    "assurance_status",
    "assurance_plan",
    "assurance_explain",
    "assurance_debt",
    "assurance_registry",
    "assurance_integrity",
}


def assurance(plane: Plane, name: str, args: dict[str, Any]) -> Any:
    """One dispatch for the assurance engine; every interface reaches the same service."""
    if name == "assurance_status":
        return assurance_service.status(plane, args.get("task_id"))
    if name == "assurance_plan":
        return assurance_service.plan_view(plane, args["task_id"])
    if name == "assurance_explain":
        return assurance_service.explain(plane, args["obligation_id"])
    if name == "assurance_debt":
        return assurance_service.debt_report(plane, args.get("task_id"))
    if name == "assurance_registry":
        return assurance_service.registry(plane)
    if name == "assurance_integrity":
        return assurance_service.integrity(plane)
    if name == "assurance_verify":
        return assurance_service.verify(plane, args["task_id"], args["session"])
    if name == "assurance_compile":
        return assurance_service.compile_plan(
            plane, args["task_id"], phase=args.get("phase", "RECONCILED")
        )
    if name == "assurance_waive":
        return assurance_service.waive(
            plane, args["obligation_id"], args["reason"], args["authorization"]
        )
    if name == "assurance_resolve_human":
        return assurance_service.resolve_human(
            plane, args["obligation_id"], args["decision"], args.get("accepted", True)
        )
    if name == "assurance_register_verifier":
        return assurance_service.register_verifier(plane, args["descriptor"])
    if name == "assurance_migrate":
        return assurance_migration.migrate(plane, dry_run=args.get("dry_run", False))
    if name == "assurance_rollback":
        return assurance_migration.rollback(plane, args["identifier"], args["reason"])
    raise ControlError("UNKNOWN_OPERATION", name)


def call(plane: Plane, name: str, args: dict[str, Any], *, local: bool = False) -> dict[str, Any]:
    require(name in SCHEMAS, "UNKNOWN_OPERATION", f"Unknown operation: {name}")
    require(
        local or name not in LOCAL_ONLY,
        "PERMISSION_DENIED",
        "Operation requires the local project owner",
    )
    errors = list(Draft202012Validator(SCHEMAS[name]).iter_errors(args))
    require(not errors, "INVALID_INPUT", "; ".join(e.message for e in errors))
    if name == "doctor":
        result: Any = doctor(plane)
    elif name == "preflight":
        result = preflight.for_plane(
            plane, repair_first=args.get("repair", True), deep=args.get("deep", True)
        )
    elif name in {"status", "knowledge_health"}:
        result = plane.status()
    elif name in {"discover_project", "reconcile"}:
        result = plane.reconcile()
    elif name == "query_knowledge":
        result = plane.knowledge.query(**args)
    elif name == "knowledge_show":
        result = plane.store.get(args["identifier"], "entity")
    elif name == "knowledge_history":
        result = plane.store.history(args["identifier"])
    elif name == "impact_analysis":
        result = plane.knowledge.impact(args["identifier"])
    elif name == "get_context":
        result = plane.context(**args)
    elif name == "get_ready_tasks":
        invalidate(plane)
        result = [
            t
            for t in plane.store.list("task")
            if t["state"] == "READY" and plane.readiness(t["id"])["status"] != "BLOCKED"
        ]
    elif name == "task_list":
        result = plane.status()["tasks"]
    elif name == "agent_join":
        result = plane.join(**args)
    elif name == "claim_task":
        result = plane.claim(**args)
    elif name == "heartbeat":
        result = plane.heartbeat(**args)
    elif name == "checkpoint_task":
        result = plane.checkpoint(**args)
    elif name == "release_task":
        result = plane.release(**args)
    elif name == "resume_task":
        result = plane.resume(**args)
    elif name == "record_evidence":
        result = verify(plane, **args)
    elif name == "complete_task":
        result = complete(plane, **args)
    elif name == "integration_gate":
        result = integration_gate(plane, **args)
    elif name == "timeline":
        result = plane.store.timeline(**args)
    elif name == "readiness":
        result = plane.readiness(**args)
    elif name == "plan_audit":
        result = plane.audit_plan(**args)
    elif name == "task_create":
        result = plane.create_task(**args)
    elif name == "task_ready":
        result = plane.ready(**args)
    elif name == "resolve_blocker":
        result = plane.resolve_blocker(**args)
    elif name == "task_transition":
        result = plane.transition(**args)
    elif name == "resolve_claim":
        result = plane.knowledge.resolve_claim(**args)
    elif name == "knowledge_apply":
        result = plane.knowledge.apply(**args)
    elif name == "knowledge_link":
        result = plane.knowledge.link(**args)
    elif name == "record_discovery":
        data = args["data"]
        if not local:
            require(
                data.get("authority") == "inference" and data.get("observation") == "INFERRED",
                "PERMISSION_DENIED",
                "Workers submit inferred claims; promotion requires owner review",
            )
        result = plane.knowledge.claim(data)
    elif name == "lifecycle":
        result = plane.knowledge.lifecycle(**args)
    elif name == "approve_command":
        result = plane.approve_command(**args)
    elif name == "workspace_refresh":
        result = refresh_workspace(plane, **args)
    elif name == "workspace_merge":
        result = merge_workspace(plane, **args)
    elif name == "workspace_create":
        result = create_workspace(plane, **args)
    elif name == "workspace_cleanup":
        result = cleanup(plane, **args)
    elif name == "parallel_safety":
        result = parallel_safety(
            plane.store.get(args["left"], "task"), plane.store.get(args["right"], "task")
        )
    elif name.startswith("assurance_"):
        result = assurance(plane, name, args)
    else:
        raise ControlError("UNKNOWN_OPERATION", name)
    return {"api_version": API_VERSION, "operation": name, "data": result}
