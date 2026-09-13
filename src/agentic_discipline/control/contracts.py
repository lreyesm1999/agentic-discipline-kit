"""Typed domain boundaries; source text is data, never executable authority."""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from pathlib import Path
from typing import Any

from ..common import AgenticError


class ControlError(AgenticError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def require(condition: Any, code: str, message: str) -> None:
    if not condition:
        raise ControlError(code, message)


def uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def encode(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )


def digest(value: Any) -> str:
    return hashlib.sha256(encode(value).encode()).hexdigest()


GRAPHS = {"requirement", "architecture", "code", "decision", "execution", "evidence", "evolution"}
LIFECYCLES = {"ACTIVE", "DEPRECATED", "SUPERSEDED", "RETIRED", "HISTORICAL", "INVALID"}
AUTHORITIES = {
    "inference": 0,
    "historical": 1,
    "documentation": 2,
    "code": 3,
    "verified": 4,
    "contract": 5,
    "human": 6,
}
OBSERVATIONS = {"INFERRED", "DECLARED", "OBSERVED", "VERIFIED", "UNKNOWN", "CONFLICTING"}
RELATIONS = {
    "depends_on",
    "specified_by",
    "verified_by",
    "planned_by",
    "implemented_by",
    "evidenced_by",
    "contains",
    "imports",
    "calls",
    "affects",
    "changes",
    "supersedes",
    "blocked_by",
    "claimed_by",
}
TRANSITIONS = {
    "PLANNED": {"READY", "BLOCKED", "CANCELLED", "SUPERSEDED"},
    "READY": {"CLAIMED", "BLOCKED", "CANCELLED", "SUPERSEDED"},
    "CLAIMED": {"RUNNING", "READY", "BLOCKED", "CANCELLED", "SUPERSEDED"},
    "RUNNING": {"VERIFYING", "READY", "BLOCKED", "FAILED", "CANCELLED", "SUPERSEDED"},
    "BLOCKED": {"READY", "CANCELLED", "SUPERSEDED"},
    "VERIFYING": {"COMPLETED", "FAILED", "READY", "BLOCKED", "CANCELLED", "SUPERSEDED"},
    "FAILED": {"READY", "CANCELLED", "SUPERSEDED"},
    "COMPLETED": {"NEEDS_REVALIDATION", "SUPERSEDED"},
    "NEEDS_REVALIDATION": {"READY", "BLOCKED", "CANCELLED", "SUPERSEDED"},
    "CANCELLED": set(),
    "SUPERSEDED": set(),
}
SECRET_RE = re.compile(
    r"(?i)(?<![a-z0-9])(?:-----BEGIN [A-Z ]*PRIVATE KEY-----|(?:sk-|ghp_|github_pat_|AKIA)[A-Za-z0-9_-]{16,}|(?:password|api[_-]?key|secret|access[_-]?token)[\"']?\s*[=:]\s*[\"']?[^\s,;\"']+)"
)
SECRET_KEYS = {"password", "api_key", "apikey", "secret", "access_token", "private_key"}


QUOTED_SECRET_RE = re.compile(
    r"(?i)(?:password|api[_-]?key|secret|access[_-]?token)[\"']?\s*[=:]\s*(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')"
)


def redact(text: str) -> str:
    return SECRET_RE.sub("[REDACTED]", QUOTED_SECRET_RE.sub("[REDACTED]", text))


def safe_data(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            require(
                str(key).lower() not in SECRET_KEYS,
                "SECRET_REJECTED",
                "Store secret references, not values",
            )
            safe_data(child)
    elif isinstance(value, list):
        for child in value:
            safe_data(child)
    elif isinstance(value, str):
        require(
            redact(value) == value, "SECRET_REJECTED", "Possible credential in persistent input"
        )


def relative_path(value: str) -> str:
    require(
        isinstance(value, str) and bool(value) and "\\" not in value,
        "INVALID_PATH",
        "Use a relative POSIX path",
    )
    p = Path(value)
    require(
        not p.is_absolute() and ".." not in p.parts and ":" not in value,
        "INVALID_PATH",
        "Path escapes repository",
    )
    require(
        not any(x in {".git", ".agentic"} for x in p.parts),
        "PROTECTED_PATH",
        "Control and Git metadata are protected",
    )
    require(
        not p.name.startswith(".env") and p.suffix not in {".pem", ".key", ".p12"},
        "SECRET_PATH",
        "Secret path is excluded",
    )
    return p.as_posix()


def entity_contract(data: dict[str, Any]) -> None:
    required = {"graph", "type", "name", "source_ref", "authority", "confidence", "observation"}
    require(
        required <= data.keys(),
        "INVALID_ENTITY",
        f"Missing entity fields: {sorted(required - data.keys())}",
    )
    require(
        isinstance(data["graph"], str) and data["graph"] in GRAPHS,
        "INVALID_GRAPH",
        "Unknown specialized graph",
    )
    for key in ("name", "type", "source_ref"):
        require(
            isinstance(data[key], str) and bool(data[key].strip()),
            "INVALID_ENTITY",
            f"{key} must be nonempty text",
        )
    require(
        isinstance(data["authority"], str) and data["authority"] in AUTHORITIES,
        "INVALID_AUTHORITY",
        "Unknown authority class",
    )
    confidence = data["confidence"]
    require(
        type(confidence) in (float, int) and math.isfinite(confidence) and 0 <= confidence <= 1,
        "INVALID_CONFIDENCE",
        "Confidence must be 0..1",
    )
    require(
        isinstance(data["observation"], str) and data["observation"] in OBSERVATIONS,
        "INVALID_OBSERVATION",
        "Unknown evidence class",
    )
    require(
        isinstance(data.get("lifecycle", "ACTIVE"), str)
        and data.get("lifecycle", "ACTIVE") in LIFECYCLES,
        "INVALID_LIFECYCLE",
        "Unknown lifecycle",
    )
    safe_data(data)


def task_contract(data: dict[str, Any]) -> None:
    required = {
        "objective",
        "scope",
        "out_of_scope",
        "requirements",
        "acceptance",
        "dependencies",
        "boundaries",
        "context",
        "verification",
        "required_evidence",
        "rollback",
        "definition_of_done",
        "risk",
        "budget",
    }
    require(
        required <= data.keys(),
        "INVALID_TASK",
        f"Missing contract fields: {sorted(required - data.keys())}",
    )
    require(
        data.keys() <= required | {"assumptions", "capabilities", "priority"},
        "INVALID_TASK",
        "Execution state is server-owned; only contract fields are accepted",
    )
    for key in ("assumptions", "capabilities"):
        require(
            isinstance(data.get(key, []), list)
            and all(isinstance(x, str) and x for x in data.get(key, [])),
            "INVALID_TASK",
            f"Invalid list: {key}",
        )
    for key in ("objective", "rollback", "definition_of_done"):
        require(
            isinstance(data[key], str) and bool(data[key].strip()),
            "INVALID_TASK",
            f"{key} must be nonempty",
        )
    for key in (
        "scope",
        "out_of_scope",
        "requirements",
        "acceptance",
        "dependencies",
        "boundaries",
        "context",
        "required_evidence",
    ):
        require(
            isinstance(data[key], list) and all(isinstance(x, str) and x for x in data[key]),
            "INVALID_TASK",
            f"Invalid list: {key}",
        )
    require(
        data["scope"] and data["acceptance"] and data["required_evidence"],
        "INVALID_TASK",
        "Scope, acceptance and evidence cannot be empty",
    )
    for path in data["scope"]:
        relative_path(path)
    require(
        isinstance(data["risk"], str) and data["risk"] in {"LOW", "STANDARD", "HIGH", "CRITICAL"},
        "INVALID_RISK",
        "Unknown risk profile",
    )
    require(
        isinstance(data["verification"], list) and data["verification"],
        "INVALID_TASK",
        "At least one verifier is required",
    )
    for verifier in data["verification"]:
        require(isinstance(verifier, dict), "INVALID_VERIFIER", "Verifier must be an object")
        require(
            {"kind", "command", "acceptance"}
            <= set(verifier)
            <= {"kind", "command", "acceptance", "inputs"},
            "INVALID_VERIFIER",
            "Verifier needs kind, command, acceptance",
        )
        require(
            verifier["kind"] in data["required_evidence"],
            "INVALID_VERIFIER",
            "Verifier kind is not required evidence",
        )
        require(
            isinstance(verifier["command"], list)
            and verifier["command"]
            and all(isinstance(x, str) and x and "\x00" not in x for x in verifier["command"]),
            "INVALID_COMMAND",
            "Use nonempty argv arrays",
        )
        require(
            isinstance(verifier["acceptance"], list)
            and all(
                type(i) is int and 0 <= i < len(data["acceptance"]) for i in verifier["acceptance"]
            ),
            "INVALID_VERIFIER",
            "Invalid acceptance indexes",
        )
    for verifier in data["verification"]:
        inputs = verifier.get("inputs", ["."])
        require(
            isinstance(inputs, list) and inputs and all(isinstance(p, str) for p in inputs),
            "INVALID_VERIFIER",
            "Verifier inputs must be nonempty paths",
        )
        for path in inputs:
            relative_path(path)
    require(
        {i for v in data["verification"] for i in v["acceptance"]}
        == set(range(len(data["acceptance"]))),
        "INVALID_TASK",
        "Every acceptance criterion needs a verifier",
    )
    require(
        {v["kind"] for v in data["verification"]} >= set(data["required_evidence"]),
        "INVALID_TASK",
        "Required evidence lacks a verifier",
    )
    budget = data["budget"]
    require(isinstance(budget, dict), "INVALID_BUDGET", "Budget must be an object")
    for key in (
        "max_runtime",
        "max_retries",
        "max_files",
        "max_lines",
        "max_external_calls",
        "max_cost",
    ):
        require(
            type(budget.get(key)) is int and budget[key] >= 0,
            "INVALID_BUDGET",
            f"{key} must be a nonnegative integer",
        )
    require(
        0 < budget["max_runtime"] <= 3600 and budget["max_files"] > 0,
        "INVALID_BUDGET",
        "Runtime must be 1..3600 seconds and max_files positive",
    )
    safe_data(data)
