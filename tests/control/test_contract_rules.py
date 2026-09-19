"""Domain contract rules asserted by exact error code and message.

Callers of the control plane branch on ``ControlError.code``; most existing tests
only checked that *some* ControlError was raised. Every case here starts from a
valid document, breaks exactly one rule, and asserts the code and message that
rule produces, plus the boundary values each comparison and set must accept.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

import pytest
from conftest import contract

from agentic_discipline.control.contracts import (
    ControlError,
    encode,
    entity_contract,
    redact,
    relative_path,
    safe_data,
    task_contract,
)

DROP = object()


def _rejects(check: Callable[[Any], object], value: Any, code: str, message: str) -> None:
    with pytest.raises(ControlError) as caught:
        check(value)
    assert (caught.value.code, str(caught.value)) == (code, message)


def _with(document: dict[str, Any], **changes: Any) -> dict[str, Any]:
    changed = copy.deepcopy(document)
    for key, value in changes.items():
        if value is DROP:
            del changed[key]
        else:
            changed[key] = value
    return changed


def _task(**changes: Any) -> dict[str, Any]:
    return _with(contract(), **changes)


def _verifier(**changes: Any) -> dict[str, Any]:
    task = contract()
    task["verification"] = [_with(task["verification"][0], **changes)]
    return task


def _budget(**changes: Any) -> dict[str, Any]:
    task = contract()
    task["budget"] = _with(task["budget"], **changes)
    return task


# --- encode, redact and safe_data ------------------------------------------------------


def test_encode_is_compact_sorted_ascii_json_without_nan() -> None:
    assert encode({"b": 1, "a": "é"}) == '{"a":"\\u00e9","b":1}'
    with pytest.raises(ValueError):
        encode(float("nan"))


def test_redact_replaces_unquoted_and_quoted_credentials() -> None:
    assert redact("password=hunter2 rest") == "[REDACTED] rest"
    assert redact('password="two words" and ok') == "[REDACTED] and ok"


@pytest.mark.parametrize(
    "value",
    [{"Password": "x"}, {"outer": {"api_key": "x"}}, ["ok", {"secret": 1}]],
    ids=["mixed-case-key", "nested-key", "key-inside-list"],
)
def test_secret_keys_are_rejected_wherever_they_appear(value: Any) -> None:
    _rejects(safe_data, value, "SECRET_REJECTED", "Store secret references, not values")


@pytest.mark.parametrize(
    "value",
    ["password=hunter2", ["token sk-abcdefghijklmnopqrstuv"], {"note": "api_key: abc123"}],
    ids=["text", "inside-list", "inside-dict"],
)
def test_credential_text_is_rejected_wherever_it_appears(value: Any) -> None:
    _rejects(safe_data, value, "SECRET_REJECTED", "Possible credential in persistent input")


def test_ordinary_nested_data_is_accepted() -> None:
    assert safe_data({"name": "value", "items": ["a", 1, {"path": "src/app.py"}]}) is None


# --- relative_path -----------------------------------------------------------------------


@pytest.mark.parametrize("value", ["src/app.py", "tests/unit/test_app.py", "environment.md"])
def test_relative_posix_paths_are_accepted(value: str) -> None:
    assert relative_path(value) == value


@pytest.mark.parametrize("value", ["", "src\\app.py", 3], ids=["empty", "backslash", "not-text"])
def test_non_posix_path_text_is_rejected(value: Any) -> None:
    _rejects(relative_path, value, "INVALID_PATH", "Use a relative POSIX path")


# Contracts are validated on one platform and executed on another, so a rooted
# POSIX path must be rejected on Windows too, where it resolves to the drive root.
@pytest.mark.parametrize(
    "value", ["../outside", "src/../../outside", "C:outside", "/etc/outside", "//server/share"]
)
def test_paths_leaving_the_repository_are_rejected(value: str) -> None:
    _rejects(relative_path, value, "INVALID_PATH", "Path escapes repository")


@pytest.mark.parametrize("value", [".git/config", "nested/.agentic/state.db"])
def test_control_and_git_metadata_are_protected(value: str) -> None:
    _rejects(relative_path, value, "PROTECTED_PATH", "Control and Git metadata are protected")


@pytest.mark.parametrize("value", [".env", "config/.env.local", "tls.pem", "id.key", "cert.p12"])
def test_secret_files_are_excluded(value: str) -> None:
    _rejects(relative_path, value, "SECRET_PATH", "Secret path is excluded")


# --- entity_contract ---------------------------------------------------------------------

ENTITY: dict[str, Any] = {
    "graph": "code",
    "type": "symbol",
    "name": "value",
    "source_ref": "app.py",
    "authority": "code",
    "confidence": 0.5,
    "observation": "OBSERVED",
}


@pytest.mark.parametrize(
    "changes",
    [{}, {"lifecycle": "RETIRED"}, {"confidence": 0}, {"confidence": 1}, {"confidence": 1.0}],
    ids=["base", "lifecycle", "confidence-0", "confidence-1", "confidence-1.0"],
)
def test_valid_entities_are_accepted(changes: dict[str, Any]) -> None:
    assert entity_contract(_with(ENTITY, **changes)) is None


ENTITY_REJECTIONS: list[tuple[str, dict[str, Any], str, str]] = [
    (
        "missing-field",
        {"observation": DROP},
        "INVALID_ENTITY",
        "Missing entity fields: ['observation']",
    ),
    ("unknown-graph", {"graph": "unknown"}, "INVALID_GRAPH", "Unknown specialized graph"),
    ("blank-name", {"name": "  "}, "INVALID_ENTITY", "name must be nonempty text"),
    ("blank-type", {"type": "  "}, "INVALID_ENTITY", "type must be nonempty text"),
    ("blank-source", {"source_ref": " "}, "INVALID_ENTITY", "source_ref must be nonempty text"),
    ("unknown-authority", {"authority": "guess"}, "INVALID_AUTHORITY", "Unknown authority class"),
    ("confidence-above-1", {"confidence": 1.5}, "INVALID_CONFIDENCE", "Confidence must be 0..1"),
    ("confidence-below-0", {"confidence": -0.1}, "INVALID_CONFIDENCE", "Confidence must be 0..1"),
    (
        "confidence-nan",
        {"confidence": float("nan")},
        "INVALID_CONFIDENCE",
        "Confidence must be 0..1",
    ),
    ("confidence-bool", {"confidence": True}, "INVALID_CONFIDENCE", "Confidence must be 0..1"),
    (
        "unknown-observation",
        {"observation": "SEEN"},
        "INVALID_OBSERVATION",
        "Unknown evidence class",
    ),
    ("unknown-lifecycle", {"lifecycle": "GONE"}, "INVALID_LIFECYCLE", "Unknown lifecycle"),
    (
        "credential-in-name",
        {"name": "password=hunter2"},
        "SECRET_REJECTED",
        "Possible credential in persistent input",
    ),
]


@pytest.mark.parametrize(
    ("changes", "code", "message"),
    [case[1:] for case in ENTITY_REJECTIONS],
    ids=[case[0] for case in ENTITY_REJECTIONS],
)
def test_entity_rule_violations_report_their_code(
    changes: dict[str, Any], code: str, message: str
) -> None:
    _rejects(entity_contract, _with(ENTITY, **changes), code, message)


# --- task_contract -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "task",
    [
        contract(),
        _task(assumptions=["cache is warm"], capabilities=["git"], priority=5),
        _task(risk="STANDARD"),
        _task(risk="HIGH"),
        _task(risk="CRITICAL"),
        _verifier(inputs=["app.py"]),
        _budget(max_runtime=1),
        _budget(max_runtime=3600, max_files=1, max_retries=0),
    ],
    ids=[
        "base",
        "optional-fields",
        "risk-standard",
        "risk-high",
        "risk-critical",
        "verifier-inputs",
        "runtime-1",
        "runtime-3600",
    ],
)
def test_valid_task_contracts_are_accepted(task: dict[str, Any]) -> None:
    assert task_contract(task) is None


LIST_FIELDS = (
    "scope",
    "out_of_scope",
    "requirements",
    "acceptance",
    "dependencies",
    "boundaries",
    "context",
    "required_evidence",
)
BUDGET_KEYS = (
    "max_runtime",
    "max_retries",
    "max_files",
    "max_lines",
    "max_external_calls",
    "max_cost",
)
RUNTIME_MESSAGE = "Runtime must be 1..3600 seconds and max_files positive"

TASK_REJECTIONS: list[tuple[str, dict[str, Any], str, str]] = [
    ("missing-field", _task(budget=DROP), "INVALID_TASK", "Missing contract fields: ['budget']"),
    (
        "server-owned-field",
        _task(state="RUNNING"),
        "INVALID_TASK",
        "Execution state is server-owned; only contract fields are accepted",
    ),
    *[
        (f"blank-{key}-entry", _task(**{key: [""]}), "INVALID_TASK", f"Invalid list: {key}")
        for key in ("assumptions", "capabilities")
    ],
    *[
        (f"blank-{key}", _task(**{key: "  "}), "INVALID_TASK", f"{key} must be nonempty")
        for key in ("objective", "rollback", "definition_of_done")
    ],
    *[
        (f"blank-{key}-entry", _task(**{key: [""]}), "INVALID_TASK", f"Invalid list: {key}")
        for key in LIST_FIELDS
    ],
    *[
        (
            f"empty-{key}",
            _task(**{key: []}),
            "INVALID_TASK",
            "Scope, acceptance and evidence cannot be empty",
        )
        for key in ("scope", "acceptance", "required_evidence")
    ],
    ("scope-escape", _task(scope=["../x"]), "INVALID_PATH", "Path escapes repository"),
    ("unknown-risk", _task(risk="EXTREME"), "INVALID_RISK", "Unknown risk profile"),
    ("no-verifier", _task(verification=[]), "INVALID_TASK", "At least one verifier is required"),
    (
        "verifier-not-object",
        _task(verification=["unit"]),
        "INVALID_VERIFIER",
        "Verifier must be an object",
    ),
    (
        "verifier-missing-command",
        _verifier(command=DROP),
        "INVALID_VERIFIER",
        "Verifier needs kind, command, acceptance",
    ),
    (
        "verifier-extra-key",
        _verifier(shell=True),
        "INVALID_VERIFIER",
        "Verifier needs kind, command, acceptance",
    ),
    (
        "verifier-kind-not-required",
        _verifier(kind="lint"),
        "INVALID_VERIFIER",
        "Verifier kind is not required evidence",
    ),
    *[
        (
            f"command-{name}",
            _verifier(command=command),
            "INVALID_COMMAND",
            "Use nonempty argv arrays",
        )
        for name, command in (
            ("empty", []),
            ("string", "python test_app.py"),
            ("blank-arg", [""]),
            ("nul-byte", ["python", "a\x00b"]),
        )
    ],
    *[
        (
            f"acceptance-{name}",
            _verifier(acceptance=indexes),
            "INVALID_VERIFIER",
            "Invalid acceptance indexes",
        )
        for name, indexes in (
            ("past-end", [1]),
            ("negative", [-1]),
            ("bool", [True]),
            ("scalar", 0),
        )
    ],
    *[
        (
            f"inputs-{name}",
            _verifier(inputs=inputs),
            "INVALID_VERIFIER",
            "Verifier inputs must be nonempty paths",
        )
        for name, inputs in (("empty", []), ("not-text", [3]), ("scalar", "app.py"))
    ],
    ("inputs-escape", _verifier(inputs=["../x"]), "INVALID_PATH", "Path escapes repository"),
    (
        "uncovered-acceptance",
        _task(acceptance=["Value is one", "Value is logged"]),
        "INVALID_TASK",
        "Every acceptance criterion needs a verifier",
    ),
    (
        "evidence-without-verifier",
        _task(required_evidence=["unit", "lint"]),
        "INVALID_TASK",
        "Required evidence lacks a verifier",
    ),
    ("budget-not-object", _task(budget="cheap"), "INVALID_BUDGET", "Budget must be an object"),
    *[
        (
            f"budget-{key}-{name}",
            _budget(**{key: value}),
            "INVALID_BUDGET",
            f"{key} must be a nonnegative integer",
        )
        for key in BUDGET_KEYS
        for name, value in (("missing", DROP), ("negative", -1), ("bool", True), ("float", 1.5))
    ],
    ("runtime-zero", _budget(max_runtime=0), "INVALID_BUDGET", RUNTIME_MESSAGE),
    ("runtime-above-limit", _budget(max_runtime=3601), "INVALID_BUDGET", RUNTIME_MESSAGE),
    ("no-files", _budget(max_files=0), "INVALID_BUDGET", RUNTIME_MESSAGE),
    (
        "credential-in-objective",
        _task(objective="password=hunter2"),
        "SECRET_REJECTED",
        "Possible credential in persistent input",
    ),
]


@pytest.mark.parametrize(
    ("task", "code", "message"),
    [case[1:] for case in TASK_REJECTIONS],
    ids=[case[0] for case in TASK_REJECTIONS],
)
def test_task_rule_violations_report_their_code(
    task: dict[str, Any], code: str, message: str
) -> None:
    _rejects(task_contract, task, code, message)


def test_a_verifier_without_inputs_does_not_excuse_the_next_ones() -> None:
    task = contract()
    (unit,) = task["verification"]
    task["verification"] = [
        {k: v for k, v in unit.items() if k != "inputs"},
        {**unit, "inputs": []},
    ]

    with pytest.raises(ControlError) as caught:
        task_contract(task)
    assert (caught.value.code, str(caught.value)) == (
        "INVALID_VERIFIER",
        "Verifier inputs must be nonempty paths",
    )
