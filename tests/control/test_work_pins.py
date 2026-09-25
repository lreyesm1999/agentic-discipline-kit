"""Exact values the work mutation survivors still change.

Each case is the branch the survivor sits on, and the assertion is the whole value, not a
substring of it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from agentic_discipline.bootstrap import initialize_project
from agentic_discipline.common import AgenticError, run_git
from agentic_discipline.control import work
from agentic_discipline.control.contracts import ControlError
from agentic_discipline.control.plane import Plane

GATE = [sys.executable, "-c", "pass"]


def _write_gates(path: Path, gates: list[dict[str, Any]]) -> None:
    config = json.loads(path.read_text(encoding="utf-8"))
    config["gates"] = gates
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")


@pytest.fixture
def plane(tmp_path: Path) -> Any:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\nname='r'\nversion='0.1'\n", encoding="utf-8")
    (root / "src" / "app.py").write_text("def compute_total():\n    return 1\n", encoding="utf-8")
    run_git(["init"], cwd=root)
    initialize_project(root)
    _write_gates(root / "agentic.config.json", [{"name": "python/tests", "command": GATE}])
    with Plane(root) as opened:
        opened.reconcile()
        yield opened


class _Store:
    def __init__(self, rows: dict[str, list[dict[str, Any]]]) -> None:
        self.rows = rows

    def list(self, kind: str) -> list[dict[str, Any]]:
        return list(self.rows.get(kind, []))

    def get(self, identifier: str) -> dict[str, Any]:
        for kind in self.rows.values():
            for row in kind:
                if row.get("id") == identifier:
                    return row
        raise KeyError(identifier)


def test_a_trailing_x_is_a_word_and_punctuation_is_not() -> None:
    assert work.terms("see appX now") == ["see", "appx", "now"]
    assert work.terms("see app. now") == ["see", "app", "now"]


def test_requirements_skip_a_non_match_and_read_statement_and_excerpt() -> None:
    store = _Store(
        {
            "entity": [
                {
                    "id": "a",
                    "graph": "requirement",
                    "lifecycle": "ACTIVE",
                    "name": "unrelated",
                },
                {
                    "id": "b",
                    "graph": "requirement",
                    "lifecycle": "ACTIVE",
                    "statement": "the total",
                },
                {
                    "id": "c",
                    "graph": "requirement",
                    "lifecycle": "ACTIVE",
                    "excerpt": "the total",
                },
            ]
        }
    )
    matched = work._requirements(SimpleNamespace(store=store), "compute the total")
    assert [entity["id"] for entity in matched] == ["b", "c"]

    # When mutmut replaces continue with break on non-matching or stale entity:
    # A store with the first entity not matching must not break the loop!
    store_first_unrelated = _Store(
        {
            "entity": [
                {
                    "id": "unrelated_1",
                    "graph": "requirement",
                    "lifecycle": "ACTIVE",
                    "name": "something else entirely",
                },
                {
                    "id": "target_req",
                    "graph": "requirement",
                    "lifecycle": "ACTIVE",
                    "statement": "important work item",
                },
            ]
        }
    )
    res = work._requirements(SimpleNamespace(store=store_first_unrelated), "important work item")
    assert len(res) == 1
    assert res[0]["id"] == "target_req"

    # Multi-word statement joining: text = " ".join(...)
    # If joined with "XX XX", overlap of multi-word phrase inside entity won't match words of request
    store_multi = _Store(
        {
            "entity": [
                {
                    "id": "multi_word",
                    "graph": "requirement",
                    "lifecycle": "ACTIVE",
                    "name": "first",
                    "statement": "second",
                    "excerpt": "third",
                }
            ]
        }
    )
    res_multi = work._requirements(SimpleNamespace(store=store_multi), "first second third")
    assert len(res_multi) == 1
    assert res_multi[0]["id"] == "multi_word"



def test_an_optional_gate_does_not_hide_the_required_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "gates"
    root.mkdir()
    (root / "agentic.config.json").write_text("{}", encoding="utf-8")

    def load(path: Path) -> dict[str, Any]:
        return {
            "gates": [
                {"name": "lint", "command": "ruff", "required": False},
                {"name": "unit tests", "command": GATE},
            ]
        }

    monkeypatch.setattr("agentic_discipline.validation.load_quality_config", load)
    verifiers, kinds, source = work._verifiers(root, 1)
    assert kinds == ["unit"]
    assert verifiers[0]["acceptance"] == [0]
    assert source == "the 1 required gates in agentic.config.json"


def test_no_required_gate_says_there_are_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "gates"
    root.mkdir()
    (root / "agentic.config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "agentic_discipline.validation.load_quality_config",
        lambda path: {"gates": [{"name": "lint", "command": "ruff", "required": False}]},
    )
    verifiers, kinds, source = work._verifiers(root, 1)
    assert (verifiers, kinds) == ([], [])
    assert source == (
        "none of the required gates in agentic.config.json proves behaviour: no gates at all"
    )


def test_risk_is_assessed_against_an_empty_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def assess(diff: str, scope: list[str]) -> Any:
        seen["diff"] = diff
        return SimpleNamespace(level="LOW", factors={"paths": False})

    monkeypatch.setattr("agentic_discipline.risk.assess_risk", assess)
    assert work._risk(["src/app.py"]) == ("LOW", [])
    assert seen["diff"] == ""


def test_stale_code_is_not_a_path_the_request_may_name(plane: Any) -> None:
    with plane.store.transaction():
        for entity in plane.store.list("entity"):
            if entity.get("path") == "src/app.py":
                plane.store.put("entity", {**entity, "stale": True}, expected=entity["version"])
    derived = work.derive(plane, "Change src/app.py please")
    assert "src/app.py" not in derived["contract"]["scope"]


def test_evidence_after_a_checkpoint_excludes_the_same_timestamp() -> None:
    store = _Store(
        {
            "evidence": [
                {"task_id": "T", "finished_at": 10.0, "result": "PASS"},
                {"task_id": "T", "finished_at": 11.0, "result": "PASS"},
            ]
        }
    )
    previous = {"payload": {"timestamp": 10.0}}
    found = work._evidence_since(SimpleNamespace(store=store), "T", previous)
    assert [record["finished_at"] for record in found] == [11.0]


def test_a_context_defaults_to_an_empty_list() -> None:
    task = {
        "id": "T",
        "state": "READY",
        "scope": ["src/app.py"],
        "objective": "add",
    }
    store = _Store({"task": [task]})
    assert work._existing(SimpleNamespace(store=store), "add a total", ["src/app.py"])["task"] is task


def test_a_later_active_lease_still_holds_the_tree() -> None:
    store = _Store(
        {
            "lease": [
                {"id": "L1", "state": "RELEASED", "task_id": "other"},
                {"id": "L2", "state": "ACTIVE", "task_id": "holder"},
            ],
            "task": [
                {"id": "other", "workspace_id": ""},
                {"id": "holder"},
            ],
        }
    )
    assert work._held_elsewhere(SimpleNamespace(store=store), "mine") == "holder"
    store.rows["task"][1]["workspace_id"] = "ws-1"
    assert work._held_elsewhere(SimpleNamespace(store=store), "mine") is None


def test_waiting_is_only_when_every_reason_is_a_dependency() -> None:
    task = {"id": "T", "dependencies": ["dep"]}
    store = _Store({"task": [{"id": "dep", "state": "READY"}]})

    def readiness(task_id: str) -> dict[str, Any]:
        return {"status": "BLOCKED", "reasons": [{"type": "dependency"}, {"type": "scope"}]}

    state = work._readiness(SimpleNamespace(store=store, readiness=readiness), task)
    assert state["state"] == "BLOCKED"
    assert state["waiting_for"] == ["dep"]

    def only_deps(task_id: str) -> dict[str, Any]:
        return {"status": "BLOCKED", "reasons": [{"type": "dependency"}]}

    waiting = work._readiness(SimpleNamespace(store=store, readiness=only_deps), task)
    assert waiting == {"state": "WAITING", "reasons": [{"type": "dependency"}], "waiting_for": ["dep"]}


def test_a_blocked_report_uses_that_reason() -> None:
    task = {"id": "T", "state": "PLANNED", "dependencies": []}
    plane = SimpleNamespace(
        readiness=lambda task_id: {"status": "BLOCKED", "reasons": [{"type": "scope"}]},
        store=_Store({"lease": [], "task": [task]}),
    )
    result = work._report(
        plane,
        {},
        {"provenance": {"request": "add a total"}},
        task,
        "derived from this request",
        [],
        claim=False,
        agent="local-agent",
        capabilities=None,
    )
    assert result["status"] == "BLOCKED"
    assert result["state"] == "BLOCKED"
    assert result["reason"] == "the task is recorded and cannot start yet"
    assert result["request"] == "add a total"


def test_a_blocked_reason_is_that_sentence() -> None:
    result = {
        "state": "BLOCKED",
        "task": {
            "id": "T",
            "state": "PLANNED",
            "objective": "add a total",
            "scope": ["src/app.py", "src/other.py"],
            "risk": "LOW",
            "required_evidence": ["unit", "static_analysis"],
        },
        "matched_by": "derived from this request",
        "session": "sess",
        "provenance": {
            "scope_from": "paths named in the request",
            "acceptance_from": "the request",
            "verifiers_from": "the gates",
        },
        "decisions": [{"question": "Which files?", "why": "none were named"}],
        "readiness": {"reasons": [{"type": "scope", "detail": "open"}]},
        "reason": "the task is recorded and cannot start yet",
    }
    text = work.render(result)
    assert text.startswith("Work state: BLOCKED\n\n")
    assert "  Scope      src/app.py, src/other.py" in text
    assert "  Evidence   unit, static_analysis" in text
    assert "  Claimed    yes, with a lease" in text
    assert "\nDerived from:\n" in text
    assert "\nWaiting on a decision that is yours to make:\n" in text
    assert "\nNot ready because:\n" in text
    assert '  - {"detail": "open", "type": "scope"}' in text
    assert text.endswith("\nReason: the task is recorded and cannot start yet")


def test_render_of_a_result_without_provenance_uses_an_empty_mapping() -> None:
    text = work.render(
        {"state": "BLOCKED", "reason": "stopped", "decisions": [], "task": None}
    )
    assert text == "Work state: BLOCKED\n\n\nReason: stopped"


def test_outstanding_reads_the_task_debt_and_passes_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    def debt_report(plane: Any, task_id: str | None = None) -> dict[str, Any]:
        assert task_id == "T"
        return {"tasks": [{"obligations": 1, "outstanding": [{"claim": "prove the total"}]}]}

    monkeypatch.setattr("agentic_discipline.control.assurance.service.enabled", lambda plane: True)
    monkeypatch.setattr("agentic_discipline.control.assurance.service.debt_report", debt_report)
    store = _Store(
        {
            "evidence": [
                {"task_id": "T", "kind": "unit", "result": "PASS"},
                {"task_id": "other", "kind": "unit", "result": "PASS"},
            ]
        }
    )
    claims = work._outstanding(
        SimpleNamespace(store=store),
        {"id": "T", "required_evidence": ["unit"], "acceptance": ["the total"]},
    )
    assert claims == ["prove the total"]

    def empty(plane: Any, task_id: str | None = None) -> dict[str, Any]:
        return {"tasks": [{"obligations": 0, "outstanding": []}]}

    monkeypatch.setattr("agentic_discipline.control.assurance.service.debt_report", empty)
    assert (
        work._outstanding(
            SimpleNamespace(store=store),
            {"id": "T", "required_evidence": ["unit"], "acceptance": ["the total"]},
        )
        == []
    )


def test_a_checkpoint_quotes_a_failing_command(plane: Any) -> None:
    started = work.start(plane, "Add a total to src/app.py", capabilities=["testing"])
    agents = [row for row in plane.store.list("agent") if row["name"] == "local-agent"]
    assert agents[-1]["capabilities"] == ["testing"]
    task, session = started["task"], started["session"]
    with plane.store.transaction():
        plane.store.put(
            "evidence",
            {
                "task_id": task["id"],
                "kind": "unit",
                "result": "FAIL",
                "exit_code": 1,
                "acceptance": [],
                "command": ["pytest", "tests"],
                "finished_at": 1.0,
            },
        )
    with plane.store.transaction():
        current = plane.store.get(task["id"])
        plane.store.put(
            "task",
            {**current, "assumptions": ["the total is an integer"]},
            expected=current["version"],
        )
    result = work.checkpoint(
        plane, task["id"], session, reason="blocked", pending=[], assumptions=None
    )
    context = result["context"]
    assert context["failures"] == ["unit: FAIL (exit 1)"]
    assert context["commands_run"] == ["pytest tests"]
    assert context["pending_issues"] == []
    assert context["assumptions"] == ["the total is an integer"]


def test_finish_uses_the_error_code_when_it_has_one_and_the_default_when_it_does_not(
    plane: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = work.start(plane, "Add a total to src/app.py")
    task, session = started["task"], started["session"]

    def coded(plane: Any, task_id: str, session: str) -> dict[str, Any]:
        raise ControlError("CONTRACT", "the contract is open")

    monkeypatch.setattr("agentic_discipline.control.verification.complete", coded)
    refused = work.finish(plane, task["id"], session)
    assert refused["code"] == "CONTRACT"
    assert refused["reason"] == "the contract is open"
    assert refused["state"] == plane.store.get(task["id"])["state"]
    assert "verification" in refused
    assert "state" in refused

    def bare(plane: Any, task_id: str, session: str) -> dict[str, Any]:
        raise AgenticError("completion was refused")

    monkeypatch.setattr("agentic_discipline.control.verification.complete", bare)
    again = work.finish(plane, task["id"], session)
    assert again["code"] == "COMPLETION_REFUSED"
    assert again["reason"] == "completion was refused"
    assert again["state"] == "VERIFYING"
    assert "state" in again
    assert "STATE" not in again and "XXstateXX" not in again


def test_outstanding_falls_back_to_acceptance_when_obligations_key_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("agentic_discipline.control.assurance.service.enabled", lambda plane: True)
    monkeypatch.setattr(
        "agentic_discipline.control.assurance.service.debt_report",
        lambda plane, task_id=None: {"tasks": [{}]},
    )
    plane = SimpleNamespace(store=_Store({"evidence": []}))
    task = {"id": "T", "required_evidence": ["unit"], "acceptance": ["prove total"]}
    assert work._outstanding(plane, task) == ["prove total"]


def test_outstanding_tolerates_missing_outstanding_key_in_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("agentic_discipline.control.assurance.service.enabled", lambda plane: True)
    monkeypatch.setattr(
        "agentic_discipline.control.assurance.service.debt_report",
        lambda plane, task_id=None: {"tasks": [{"obligations": 1}]},
    )
    plane = SimpleNamespace(store=_Store({"evidence": []}))
    task = {"id": "T", "required_evidence": ["unit"], "acceptance": ["prove total"]}
    assert work._outstanding(plane, task) == []


def test_outstanding_does_not_count_passing_evidence_from_another_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("agentic_discipline.control.assurance.service.enabled", lambda plane: False)
    plane = SimpleNamespace(
        store=_Store({
            "evidence": [{"task_id": "OTHER", "kind": "unit", "result": "PASS"}]
        })
    )
    task = {"id": "T", "required_evidence": ["unit"], "acceptance": ["prove total"]}
    assert work._outstanding(plane, task) == ["prove total"]


def test_outstanding_handles_debt_report_without_tasks_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("agentic_discipline.control.assurance.service.enabled", lambda plane: True)
    monkeypatch.setattr(
        "agentic_discipline.control.assurance.service.debt_report",
        lambda plane, task_id=None: {},
    )
    plane = SimpleNamespace(store=_Store({"evidence": []}))
    task = {"id": "T", "required_evidence": ["unit"], "acceptance": ["prove total"]}
    assert work._outstanding(plane, task) == ["prove total"]


def test_readiness_dependency_in_completed_state_is_not_waiting() -> None:
    task = {"id": "T", "dependencies": ["dep"]}
    store = _Store({"task": [{"id": "dep", "state": "COMPLETED"}]})
    plane = SimpleNamespace(
        store=store,
        readiness=lambda task_id: {"status": "BLOCKED", "reasons": [{"type": "scope"}]},
    )
    res = work._readiness(plane, task)
    assert res["state"] == "BLOCKED"
    assert res["waiting_for"] == []
    assert "reasons" in res
    assert res["reasons"] == [{"type": "scope"}]


def test_report_held_elsewhere_ignores_own_lease() -> None:
    task = {"id": "T", "state": "READY", "dependencies": []}
    lease = {"id": "L", "state": "ACTIVE", "task_id": "T"}
    store = _Store({"lease": [lease], "task": [task]})
    plane = SimpleNamespace(
        store=store,
        readiness=lambda task_id: {"status": "READY", "reasons": []},
        root=".",
    )
    rep = work._report(
        plane,
        {},
        {"provenance": {"request": "do total"}},
        task,
        "derived",
        [],
        claim=False,
        agent="agent",
        capabilities=None,
    )
    assert rep["state"] == "READY"
    assert rep["status"] == "PASS"


def test_checkpoint_passes_clean_evidence_and_custom_summary(plane: Any) -> None:
    started = work.start(plane, "Add a total to src/app.py")
    task, session = started["task"], started["session"]
    with plane.store.transaction():
        plane.store.put(
            "evidence",
            {
                "task_id": task["id"],
                "kind": "unit",
                "result": "PASS",
                "exit_code": 0,
                "command": ["pytest"],
                "finished_at": 1.0,
                "acceptance": [],
            },
        )
    result = work.checkpoint(
        plane, task["id"], session, reason="slice_complete", summary=["custom summary"]
    )
    ctx = result["context"]
    assert ctx["failures"] == []
    assert ctx["completed_work"] == ["custom summary"]


def test_checkpoint_counts_only_this_task_proven_evidence(plane: Any) -> None:
    started = work.start(plane, "Add a total to src/app.py")
    task, session = started["task"], started["session"]
    with plane.store.transaction():
        plane.store.put(
            "evidence",
            {
                "task_id": "OTHER",
                "kind": "unit",
                "result": "PASS",
                "exit_code": 0,
                "command": ["pytest"],
                "finished_at": 1.0,
                "acceptance": [],
            },
        )
    result = work.checkpoint(plane, task["id"], session, reason="slice_complete", summary=None)
    assert result["context"]["completed_work"] == ["no verified work yet"]


def test_checkpoint_multiple_proven_kinds_are_comma_separated(plane: Any) -> None:
    started = work.start(plane, "Add a total to src/app.py")
    task, session = started["task"], started["session"]
    with plane.store.transaction():
        plane.store.put(
            "evidence",
            {
                "task_id": task["id"],
                "kind": "lint",
                "result": "PASS",
                "exit_code": 0,
                "command": ["ruff"],
                "finished_at": 1.0,
                "acceptance": [],
            },
        )
        plane.store.put(
            "evidence",
            {
                "task_id": task["id"],
                "kind": "unit",
                "result": "PASS",
                "exit_code": 0,
                "command": ["pytest"],
                "finished_at": 2.0,
                "acceptance": [],
            },
        )
    # Take a first checkpoint to consume the new evidence
    work.checkpoint(plane, task["id"], session, reason="slice_complete")
    # Second checkpoint has no new evidence, so it formats proven_all
    second = work.checkpoint(plane, task["id"], session, reason="slice_complete")
    assert second["context"]["completed_work"] == ["previously verified: lint, unit"]


def test_derive_critical_risk_decision_why_string(
    plane: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "agentic_discipline.control.work._risk",
        lambda scope: ("CRITICAL", ["auth"]),
    )
    derived = work.derive(plane, "Update src/app.py")
    critical_decision = next(d for d in derived["decisions"] if d["decision"] == "critical_risk")
    assert critical_decision["why"] == (
        "the project's own risk rules classify this scope as CRITICAL, which"
        " requires explicit human acceptance: auth"
    )

    # When signals is empty, fallback to 'critical paths'
    # Mutants test `and` vs `or`: `', '.join(signals) and 'critical paths'` produces '' when signals is empty!
    monkeypatch.setattr(
        "agentic_discipline.control.work._risk",
        lambda scope: ("CRITICAL", []),
    )
    derived_empty = work.derive(plane, "Update src/app.py")
    crit_empty = next(d for d in derived_empty["decisions"] if d["decision"] == "critical_risk")
    assert crit_empty["why"] == (
        "the project's own risk rules classify this scope as CRITICAL, which"
        " requires explicit human acceptance: critical paths"
    )
    assert "critical paths" in crit_empty["why"]

    # When signals has items, `or 'critical paths'` must produce the signals, not 'critical paths'
    monkeypatch.setattr(
        "agentic_discipline.control.work._risk",
        lambda scope: ("CRITICAL", ["payment_module"]),
    )
    derived_with_signal = work.derive(plane, "Update src/app.py")
    crit_sig = next(d for d in derived_with_signal["decisions"] if d["decision"] == "critical_risk")
    assert "payment_module" in crit_sig["why"]
    assert "critical paths" not in crit_sig["why"]
    assert crit_sig["why"].startswith("the project's own risk rules classify this scope as CRITICAL, which requires explicit human acceptance: ")
    assert "THE PROJECT'S OWN RISK RULES" not in crit_sig["why"]



def test_finish_populates_verification_artifact_on_blocked_status(
    plane: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = work.start(plane, "Add a total to src/app.py")
    task, session = started["task"], started["session"]

    def failing_verify(plane: Any, task_id: str, session: str) -> dict[str, Any]:
        return {
            "status": "FAIL",
            "verification": {"evidence": ["some_run"]},
            "outstanding": ["do tests"],
            "state": "CLAIMED",
        }

    monkeypatch.setattr("agentic_discipline.control.work.verify", failing_verify)
    res = work.finish(plane, task["id"], session)
    assert res["status"] == "BLOCKED"
    assert res["code"] == "VERIFICATION_FAILED"
    assert res["state"] == "CLAIMED"
    assert res["verification"] == {"evidence": ["some_run"]}
    assert "verification" in res
    assert "VERIFICATION" not in res and "XXverificationXX" not in res


def test_finish_with_pre_verified_task_has_none_verification(
    plane: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = work.start(plane, "Add a total to src/app.py")
    task, session = started["task"], started["session"]

    with plane.store.transaction():
        cur = plane.store.get(task["id"])
        plane.store.put("task", {**cur, "state": "READY"}, expected=cur["version"])

    def ok_complete(plane: Any, task_id: str, session: str) -> dict[str, Any]:
        return {"completed": True}

    monkeypatch.setattr("agentic_discipline.control.verification.complete", ok_complete)
    res = work.finish(plane, task["id"], session)
    assert res["status"] == "PASS"
    assert res["verification"] is None
    assert res["state"] == "READY"


def test_requirements_multi_word_and_stale_entity_handling() -> None:
    store = _Store(
        {
            "entity": [
                {
                    "id": "stale_req",
                    "graph": "requirement",
                    "lifecycle": "ACTIVE",
                    "stale": True,
                    "statement": "compute total",
                },
                {
                    "id": "active_multi",
                    "graph": "requirement",
                    "lifecycle": "ACTIVE",
                    "statement": "compute",
                    "excerpt": "total",
                },
            ]
        }
    )
    matched = work._requirements(SimpleNamespace(store=store), "compute total")
    assert [e["id"] for e in matched] == ["active_multi"]


def test_finish_verification_field_is_preserved_when_completion_fails_with_agentic_error(
    plane: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = work.start(plane, "Add a total to src/app.py")
    task, session = started["task"], started["session"]

    def pass_verify(plane: Any, task_id: str, session: str) -> dict[str, Any]:
        return {
            "status": "PASS",
            "verification": {"evidence": ["run_passed"]},
            "outstanding": [],
            "state": "CLAIMED",
        }

    def failing_complete(plane: Any, task_id: str, session: str) -> dict[str, Any]:
        raise ControlError("INTEGRATION_FAILED", "integration checks failed")

    monkeypatch.setattr("agentic_discipline.control.work.verify", pass_verify)
    monkeypatch.setattr("agentic_discipline.control.verification.complete", failing_complete)

    res = work.finish(plane, task["id"], session)
    assert res["status"] == "BLOCKED"
    assert res["code"] == "INTEGRATION_FAILED"
    assert res["verification"] == {"evidence": ["run_passed"]}
    assert "verification" in res


def test_finish_verification_field_is_preserved_on_successful_completion(
    plane: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = work.start(plane, "Add a total to src/app.py")
    task, session = started["task"], started["session"]

    def pass_verify(plane: Any, task_id: str, session: str) -> dict[str, Any]:
        return {
            "status": "PASS",
            "verification": {"evidence": ["run_passed_ok"]},
            "outstanding": [],
            "state": "CLAIMED",
        }

    def ok_complete(plane: Any, task_id: str, session: str) -> dict[str, Any]:
        return {"done": True}

    monkeypatch.setattr("agentic_discipline.control.work.verify", pass_verify)
    monkeypatch.setattr("agentic_discipline.control.verification.complete", ok_complete)

    res = work.finish(plane, task["id"], session)
    assert res["status"] == "PASS"
    assert res["verification"] == {"evidence": ["run_passed_ok"]}
    assert "verification" in res
    assert "VERIFICATION" not in res and "XXverificationXX" not in res


def test_render_with_omitted_provenance_key() -> None:
    # When provenance key is not present in result at all, get("provenance", {}) returns {}
    # Mutants replace default {} with None, causing if provenance to fail or crash if None
    result_without_key = {
        "state": "READY",
        "task": None,
        "decisions": [],
        "reason": "ready",
    }
    rendered = work.render(result_without_key)
    assert "Derived from:" not in rendered
    assert "Work state: READY\n\n\nReason: ready" == rendered

    # When provenance is {} explicitly
    result_empty = {
        "state": "READY",
        "task": None,
        "decisions": [],
        "reason": "ready",
        "provenance": {},
    }
    assert work.render(result_empty) == rendered

    # When provenance has entries
    result_with_prov = {
        "state": "READY",
        "task": None,
        "decisions": [],
        "reason": "ready",
        "provenance": {
            "scope_from": "from_test",
            "acceptance_from": "acc_test",
            "verifiers_from": "ver_test",
        },
    }
    rendered_prov = work.render(result_with_prov)
    assert "Derived from:" in rendered_prov
    assert "  scope       from_test" in rendered_prov


def test_terms_strips_punctuation_characters_and_survives_partial_strips() -> None:
    # Mutants replace ".-/" with "XX.-/XX"
    # A token with leading 'X' or trailing 'X' must not be stripped!
    # A token like "...hello---" stripped by ".-/" produces "hello".
    # Stripped by "XX.-/XX" with leading/trailing X:
    # "Xhello" stripped of "XX.-/XX" loses 'X'! But stripped of ".-/" keeps 'X'!
    assert work.terms("XhelloX") == ["xhellox"]
    assert work.terms(".XhelloX.") == ["xhellox"]
    assert work.terms("-hello-") == ["hello"]
    assert work.terms("/hello/") == ["hello"]
    assert work.terms(".hello.") == ["hello"]
    assert work.terms("...hello...") == ["hello"]
    assert work.terms("///hello///") == ["hello"]
    assert work.terms("---hello---") == ["hello"]
    assert work.terms("X-hello-X") == ["x-hello-x"]





def test_render_preserves_blank_lines_around_sections() -> None:
    result = {
        "state": "READY",
        "task": {
            "id": "T",
            "state": "CLAIMED",
            "objective": "obj",
            "scope": ["src/app.py"],
            "risk": "LOW",
            "required_evidence": ["unit"],
        },
        "matched_by": "matched",
        "session": "sess",
        "provenance": {
            "scope_from": "request",
            "acceptance_from": "request",
            "verifiers_from": "config",
        },
        "decisions": [{"question": "Q?", "why": "W"}],
        "readiness": {"reasons": [{"type": "scope", "detail": "open"}]},
        "reason": "ready",
    }
    rendered = work.render(result)
    assert "\n\nDerived from:\n" in rendered
    assert "\n\nWaiting on a decision that is yours to make:\n" in rendered
    assert "\n\nNot ready because:\n" in rendered
    assert "  Claimed    yes, with a lease\n" in rendered


def test_terms_does_not_strip_surrounding_letter_x() -> None:
    assert "xapix" in work.terms("modify XapiX now")

