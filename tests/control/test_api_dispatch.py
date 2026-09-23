"""Versioned API dispatch, operation by operation.

`call` is the single entry point shared by the CLI, MCP and console. Existing tests
drove a few operations end to end, so an operation could reach the wrong plane
method, drop or rename an argument, skip the local-owner guard or return a different
envelope without failing. Each case records the exact call an operation makes on a
plane that only records.
"""

from __future__ import annotations

from typing import Any, Callable

import pytest
from jsonschema import Draft202012Validator

from agentic_discipline.control import api
from agentic_discipline.control.api import LOCAL_ONLY, READ_ONLY, SCHEMAS, call, schema
from agentic_discipline.control.contracts import ControlError

MODULE_FUNCTIONS = (
    "doctor",
    "invalidate",
    "verify",
    "complete",
    "integration_gate",
    "refresh_workspace",
    "merge_workspace",
    "create_workspace",
    "cleanup",
    "parallel_safety",
    "assurance_service",
    "assurance_migration",
    "preflight",
    "work",
)
TASKS = [
    {"id": "TASK-A", "state": "READY"},
    {"id": "TASK-B", "state": "READY"},
    {"id": "TASK-C", "state": "CLAIMED"},
]


class Recorder:
    """Records every call made through it and returns a value naming the call."""

    def __init__(self, name: str, log: list[Any], returns: dict[str, Callable[..., Any]]) -> None:
        self._name, self._log, self._returns = name, log, returns

    def __getattr__(self, attribute: str) -> Recorder:
        return Recorder(f"{self._name}.{attribute}", self._log, self._returns)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self._log.append((self._name, args, kwargs))
        if self._name in self._returns:
            return self._returns[self._name](*args, **kwargs)
        return ("result", self._name)


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> tuple[Recorder, list[Any]]:
    log: list[Any] = []
    returns: dict[str, Callable[..., Any]] = {
        "plane.status": lambda: {"tasks": ["TASK-A"]},
        "plane.store.list": lambda kind: TASKS,
        "plane.readiness": lambda task_id: {
            "status": "BLOCKED" if task_id == "TASK-B" else "READY"
        },
    }
    plane = Recorder("plane", log, returns)
    for function in MODULE_FUNCTIONS:
        monkeypatch.setattr(api, function, Recorder(function, log, returns))
    return plane, log


def _session(**extra: Any) -> dict[str, Any]:
    return {"task_id": "TASK-A", "session": "token", **extra}


PLANE = "plane"
# (operation, arguments, calls as (name, positional without plane, keywords), data)
DISPATCH: list[
    tuple[str, dict[str, Any], list[tuple[str, tuple[Any, ...], dict[str, Any]]], Any]
] = [
    ("doctor", {}, [("doctor", (PLANE,), {})], ("result", "doctor")),
    ("status", {}, [("plane.status", (), {})], {"tasks": ["TASK-A"]}),
    ("knowledge_health", {}, [("plane.status", (), {})], {"tasks": ["TASK-A"]}),
    ("discover_project", {}, [("plane.reconcile", (), {})], ("result", "plane.reconcile")),
    ("reconcile", {}, [("plane.reconcile", (), {})], ("result", "plane.reconcile")),
    (
        "query_knowledge",
        {"text": "orders", "historical": True, "limit": 5},
        [("plane.knowledge.query", (), {"text": "orders", "historical": True, "limit": 5})],
        ("result", "plane.knowledge.query"),
    ),
    (
        "knowledge_show",
        {"identifier": "ENT-1"},
        [("plane.store.get", ("ENT-1", "entity"), {})],
        ("result", "plane.store.get"),
    ),
    (
        "knowledge_history",
        {"identifier": "ENT-1"},
        [("plane.store.history", ("ENT-1",), {})],
        ("result", "plane.store.history"),
    ),
    (
        "impact_analysis",
        {"identifier": "ENT-1"},
        [("plane.knowledge.impact", ("ENT-1",), {})],
        ("result", "plane.knowledge.impact"),
    ),
    (
        "get_context",
        {"task_id": "TASK-A", "budget": 500},
        [("plane.context", (), {"task_id": "TASK-A", "budget": 500})],
        ("result", "plane.context"),
    ),
    (
        "get_ready_tasks",
        {},
        [
            ("invalidate", (PLANE,), {}),
            ("plane.store.list", ("task",), {}),
            ("plane.readiness", ("TASK-A",), {}),
            ("plane.readiness", ("TASK-B",), {}),
        ],
        [TASKS[0]],
    ),
    ("task_list", {}, [("plane.status", (), {})], ["TASK-A"]),
    (
        "agent_join",
        {"name": "worker", "capabilities": ["code"]},
        [("plane.join", (), {"name": "worker", "capabilities": ["code"]})],
        ("result", "plane.join"),
    ),
    (
        "claim_task",
        _session(seconds=60),
        [("plane.claim", (), _session(seconds=60))],
        ("result", "plane.claim"),
    ),
    (
        "heartbeat",
        _session(seconds=60),
        [("plane.heartbeat", (), _session(seconds=60))],
        ("result", "plane.heartbeat"),
    ),
    (
        "checkpoint_task",
        _session(data={"next_action": "test"}),
        [("plane.checkpoint", (), _session(data={"next_action": "test"}))],
        ("result", "plane.checkpoint"),
    ),
    (
        "release_task",
        _session(blocker="decision"),
        [("plane.release", (), _session(blocker="decision"))],
        ("result", "plane.release"),
    ),
    (
        "resume_task",
        _session(budget=900),
        [("plane.resume", (), _session(budget=900))],
        ("result", "plane.resume"),
    ),
    ("record_evidence", _session(), [("verify", (PLANE,), _session())], ("result", "verify")),
    ("complete_task", _session(), [("complete", (PLANE,), _session())], ("result", "complete")),
    (
        "integration_gate",
        _session(),
        [("integration_gate", (PLANE,), _session())],
        ("result", "integration_gate"),
    ),
    (
        "timeline",
        {"identifier": "TASK-A", "limit": 5},
        [("plane.store.timeline", (), {"identifier": "TASK-A", "limit": 5})],
        ("result", "plane.store.timeline"),
    ),
    (
        "readiness",
        {"task_id": "TASK-A"},
        [("plane.readiness", (), {"task_id": "TASK-A"})],
        {"status": "READY"},
    ),
    (
        "plan_audit",
        {"plan": {"tasks": []}},
        [("plane.audit_plan", (), {"plan": {"tasks": []}})],
        ("result", "plane.audit_plan"),
    ),
    (
        "task_create",
        {"contract": {"objective": "x"}},
        [("plane.create_task", (), {"contract": {"objective": "x"}})],
        ("result", "plane.create_task"),
    ),
    (
        "task_ready",
        {"task_id": "TASK-A"},
        [("plane.ready", (), {"task_id": "TASK-A"})],
        ("result", "plane.ready"),
    ),
    (
        "resolve_blocker",
        {"task_id": "TASK-A", "decision": "thirty days"},
        [("plane.resolve_blocker", (), {"task_id": "TASK-A", "decision": "thirty days"})],
        ("result", "plane.resolve_blocker"),
    ),
    (
        "task_transition",
        {"task_id": "TASK-A", "state": "CANCELLED", "reason": "dropped"},
        [
            (
                "plane.transition",
                (),
                {"task_id": "TASK-A", "state": "CANCELLED", "reason": "dropped"},
            )
        ],
        ("result", "plane.transition"),
    ),
    (
        "resolve_claim",
        {"identifier": "CLAI-1", "reason": "confirmed"},
        [("plane.knowledge.resolve_claim", (), {"identifier": "CLAI-1", "reason": "confirmed"})],
        ("result", "plane.knowledge.resolve_claim"),
    ),
    (
        "knowledge_apply",
        {"changes": [{"name": "x"}], "base_version": 0, "reason": "seed"},
        [
            (
                "plane.knowledge.apply",
                (),
                {"changes": [{"name": "x"}], "base_version": 0, "reason": "seed"},
            )
        ],
        ("result", "plane.knowledge.apply"),
    ),
    (
        "knowledge_link",
        {"source": "ENT-1", "target": "ENT-2", "relation": "depends_on"},
        [
            (
                "plane.knowledge.link",
                (),
                {"source": "ENT-1", "target": "ENT-2", "relation": "depends_on"},
            )
        ],
        ("result", "plane.knowledge.link"),
    ),
    (
        "record_discovery",
        {"data": {"authority": "human"}},
        [("plane.knowledge.claim", ({"authority": "human"},), {})],
        ("result", "plane.knowledge.claim"),
    ),
    (
        "lifecycle",
        {"identifier": "ENT-1", "state": "RETIRED", "reason": "gone"},
        [
            (
                "plane.knowledge.lifecycle",
                (),
                {"identifier": "ENT-1", "state": "RETIRED", "reason": "gone"},
            )
        ],
        ("result", "plane.knowledge.lifecycle"),
    ),
    (
        "approve_command",
        {"command": ["python", "-V"]},
        [("plane.approve_command", (), {"command": ["python", "-V"]})],
        ("result", "plane.approve_command"),
    ),
    (
        "workspace_refresh",
        {"task_id": "TASK-A"},
        [("refresh_workspace", (PLANE,), {"task_id": "TASK-A"})],
        ("result", "refresh_workspace"),
    ),
    (
        "workspace_merge",
        _session(),
        [("merge_workspace", (PLANE,), _session())],
        ("result", "merge_workspace"),
    ),
    (
        "workspace_create",
        {"task_id": "TASK-A"},
        [("create_workspace", (PLANE,), {"task_id": "TASK-A"})],
        ("result", "create_workspace"),
    ),
    (
        "workspace_cleanup",
        {"task_id": "TASK-A"},
        [("cleanup", (PLANE,), {"task_id": "TASK-A"})],
        ("result", "cleanup"),
    ),
    (
        "parallel_safety",
        {"left": "TASK-A", "right": "TASK-B"},
        [
            ("plane.store.get", ("TASK-A", "task"), {}),
            ("plane.store.get", ("TASK-B", "task"), {}),
            (
                "parallel_safety",
                (("result", "plane.store.get"), ("result", "plane.store.get")),
                {},
            ),
        ],
        ("result", "parallel_safety"),
    ),
    (
        "assurance_status",
        {"task_id": "TASK-A"},
        [("assurance_service.status", (PLANE, "TASK-A"), {})],
        ("result", "assurance_service.status"),
    ),
    (
        "assurance_plan",
        {"task_id": "TASK-A"},
        [("assurance_service.plan_view", (PLANE, "TASK-A"), {})],
        ("result", "assurance_service.plan_view"),
    ),
    (
        "assurance_explain",
        {"obligation_id": "PO-1"},
        [("assurance_service.explain", (PLANE, "PO-1"), {})],
        ("result", "assurance_service.explain"),
    ),
    (
        "assurance_debt",
        {"task_id": "TASK-A"},
        [("assurance_service.debt_report", (PLANE, "TASK-A"), {})],
        ("result", "assurance_service.debt_report"),
    ),
    (
        "assurance_registry",
        {},
        [("assurance_service.registry", (PLANE,), {})],
        ("result", "assurance_service.registry"),
    ),
    (
        "assurance_integrity",
        {},
        [("assurance_service.integrity", (PLANE,), {})],
        ("result", "assurance_service.integrity"),
    ),
    (
        "assurance_verify",
        _session(),
        [("assurance_service.verify", (PLANE, "TASK-A", "token"), {})],
        ("result", "assurance_service.verify"),
    ),
    (
        "assurance_compile",
        {"task_id": "TASK-A", "phase": "INITIAL"},
        [("assurance_service.compile_plan", (PLANE, "TASK-A"), {"phase": "INITIAL"})],
        ("result", "assurance_service.compile_plan"),
    ),
    (
        "assurance_waive",
        {"obligation_id": "PO-1", "reason": "accepted risk", "authorization": "owner"},
        [("assurance_service.waive", (PLANE, "PO-1", "accepted risk", "owner"), {})],
        ("result", "assurance_service.waive"),
    ),
    (
        "assurance_resolve_human",
        {"obligation_id": "PO-1", "decision": "hierarchy matches", "accepted": True},
        [
            (
                "assurance_service.resolve_human",
                (PLANE, "PO-1", "hierarchy matches", True),
                {},
            )
        ],
        ("result", "assurance_service.resolve_human"),
    ),
    (
        "assurance_register_verifier",
        {"descriptor": {"id": "golden"}},
        [("assurance_service.register_verifier", (PLANE, {"id": "golden"}), {})],
        ("result", "assurance_service.register_verifier"),
    ),
    (
        "assurance_migrate",
        {"dry_run": True},
        [("assurance_migration.migrate", (PLANE,), {"dry_run": True})],
        ("result", "assurance_migration.migrate"),
    ),
    (
        "assurance_rollback",
        {"identifier": "ASSU-1", "reason": "reverting the upgrade"},
        [("assurance_migration.rollback", (PLANE, "ASSU-1", "reverting the upgrade"), {})],
        ("result", "assurance_migration.rollback"),
    ),
    (
        "preflight",
        {},
        [("preflight.for_plane", (PLANE,), {"repair_first": True, "deep": True})],
        ("result", "preflight.for_plane"),
    ),
    (
        "work_start",
        {"request": "Add cancellation to src/app.py"},
        [
            (
                "work.start",
                (PLANE, "Add cancellation to src/app.py"),
                {"agent": "local-agent", "capabilities": None, "claim": True},
            )
        ],
        ("result", "work.start"),
    ),
    (
        "work_derive",
        {"request": "Add cancellation to src/app.py"},
        [("work.derive", (PLANE, "Add cancellation to src/app.py"), {})],
        ("result", "work.derive"),
    ),
]


def _normalize(log: list[Any], plane: Recorder) -> list[Any]:
    return [
        (name, tuple(PLANE if a is plane else a for a in args), kwargs)
        for name, args, kwargs in log
    ]


def test_every_operation_is_dispatched() -> None:
    assert {operation for operation, *_ in DISPATCH} == set(SCHEMAS)


@pytest.mark.parametrize(
    ("operation", "arguments", "calls", "data"), DISPATCH, ids=[d[0] for d in DISPATCH]
)
def test_operation_makes_its_exact_call_and_wraps_the_result(
    recorded: tuple[Recorder, list[Any]],
    operation: str,
    arguments: dict[str, Any],
    calls: list[Any],
    data: Any,
) -> None:
    plane, log = recorded
    assert call(plane, operation, arguments, local=True) == {
        "api_version": "2",
        "operation": operation,
        "data": data,
    }
    assert _normalize(log, plane) == calls


def test_unknown_operations_are_refused(recorded: tuple[Recorder, list[Any]]) -> None:
    plane, log = recorded
    with pytest.raises(ControlError) as caught:
        call(plane, "drop_database", {}, local=True)
    assert (caught.value.code, str(caught.value)) == (
        "UNKNOWN_OPERATION",
        "Unknown operation: drop_database",
    )
    assert log == []


def test_a_declared_operation_without_a_handler_is_refused(
    recorded: tuple[Recorder, list[Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    plane, log = recorded
    monkeypatch.setitem(SCHEMAS, "future_operation", schema({}))
    with pytest.raises(ControlError) as caught:
        call(plane, "future_operation", {}, local=True)
    assert (caught.value.code, str(caught.value)) == ("UNKNOWN_OPERATION", "future_operation")
    assert log == []


def test_owner_operations_are_listed_and_refused_to_workers(
    recorded: tuple[Recorder, list[Any]],
) -> None:
    assert LOCAL_ONLY == {
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
        "preflight",
        "work_start",
        "work_derive",
    }
    plane, log = recorded
    arguments = {operation: args for operation, args, *_ in DISPATCH}
    for operation in sorted(LOCAL_ONLY):
        with pytest.raises(ControlError) as caught:
            call(plane, operation, arguments[operation])
        assert (caught.value.code, str(caught.value)) == (
            "PERMISSION_DENIED",
            "Operation requires the local project owner",
        )
    assert log == []
    assert call(plane, "status", {})["data"] == {"tasks": ["TASK-A"]}


def test_read_only_operations_are_listed() -> None:
    assert READ_ONLY == {
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
    assert not READ_ONLY & LOCAL_ONLY


@pytest.mark.parametrize(
    ("operation", "arguments"),
    [
        ("claim_task", {}),
        ("claim_task", {"task_id": "", "session": "token", "extra": 1}),
        ("get_context", {"task_id": "TASK-A", "budget": 0}),
        ("status", {"verbose": True}),
    ],
)
def test_invalid_input_reports_every_schema_error(
    recorded: tuple[Recorder, list[Any]], operation: str, arguments: dict[str, Any]
) -> None:
    plane, log = recorded
    messages = [e.message for e in Draft202012Validator(SCHEMAS[operation]).iter_errors(arguments)]
    assert messages

    with pytest.raises(ControlError) as caught:
        call(plane, operation, arguments, local=True)

    assert (caught.value.code, str(caught.value)) == ("INVALID_INPUT", "; ".join(messages))
    assert log == []


def test_schema_helper_requires_every_property_unless_told_otherwise() -> None:
    assert schema({"a": {"type": "string"}}) == {
        "type": "object",
        "properties": {"a": {"type": "string"}},
        "required": ["a"],
        "additionalProperties": False,
    }
    assert schema({"a": {"type": "string"}}, [])["required"] == []
    assert SCHEMAS["get_context"]["required"] == ["task_id"]


@pytest.mark.parametrize(
    ("data", "allowed"),
    [
        ({"authority": "inference", "observation": "INFERRED"}, True),
        ({"authority": "inference", "observation": "DECLARED"}, False),
        ({"authority": "human", "observation": "INFERRED"}, False),
        ({}, False),
    ],
)
def test_workers_may_only_record_inferred_discoveries(
    recorded: tuple[Recorder, list[Any]], data: dict[str, Any], allowed: bool
) -> None:
    plane, log = recorded
    if allowed:
        assert call(plane, "record_discovery", {"data": data})["data"] == (
            "result",
            "plane.knowledge.claim",
        )
        assert log == [("plane.knowledge.claim", (data,), {})]
        return
    with pytest.raises(ControlError) as caught:
        call(plane, "record_discovery", {"data": data})
    assert (caught.value.code, str(caught.value)) == (
        "PERMISSION_DENIED",
        "Workers submit inferred claims; promotion requires owner review",
    )
    assert log == []
