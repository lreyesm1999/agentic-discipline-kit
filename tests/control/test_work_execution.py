"""Checkpoint, verification and completion, taken automatically and refused honestly.

The point of these is that the user never asks for a checkpoint, never says "now run the
tests", and never gets a completed task that nothing proved. So each case drives the real
cycle - a real claim, real commands, real evidence - and checks both the automation and the
refusals.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline.bootstrap import initialize_project
from agentic_discipline.common import run_git
from agentic_discipline.control import work
from agentic_discipline.control.contracts import ControlError
from agentic_discipline.control.plane import Plane

REQUEST = "Add a total to src/app.py"


def _gates(root: Path, names: set[str]) -> None:
    """Keep only the gates whose executables exist here, the way a project would."""

    path = root / "agentic.config.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    config["gates"] = [
        gate for gate in config["gates"] if isinstance(gate, dict) and gate.get("name") in names
    ]
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")


@pytest.fixture
def plane(tmp_path: Path) -> Any:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='r'\nversion='0.1'\n", encoding="utf-8")
    (root / "src" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "tests" / "test_app.py").write_text(
        "def test_ok() -> None:\n    pass\n", encoding="utf-8"
    )
    run_git(["init"], cwd=root)
    initialize_project(root)
    _gates(root, {"python/tests", "python/lint"})
    with Plane(root) as opened:
        opened.reconcile()
        yield opened


def _start(plane: Any) -> tuple[dict[str, Any], str]:
    started = work.start(plane, REQUEST)
    assert started["session"]
    return started["task"], str(started["session"])


def _edit(plane: Any) -> None:
    (Path(plane.root) / "src" / "app.py").write_text("VALUE = 1\nTOTAL = 2\n", encoding="utf-8")


def test_a_checkpoint_fills_in_everything_that_can_be_measured(plane: Any) -> None:
    task, session = _start(plane)
    _edit(plane)

    result = work.checkpoint(
        plane, task["id"], session, reason="slice_complete", summary=["added the total"]
    )

    context = result["context"]
    assert result["status"] == "PASS"
    assert context["completed_work"] == ["added the total"]
    # Measured, not retyped: the files come from the tree, the rest from the records.
    assert context["modified_files"] == ["src/app.py"]
    assert (context["commands_run"], context["failures"]) == ([], [])
    assert context["current_hypothesis"] == f"{REQUEST} (slice complete)"
    # The next action is the first thing still unproven, which the obligations decide.
    assert context["next_action"] == f"prove: {REQUEST}"
    assert context["pending_issues"] == [REQUEST]


def test_a_checkpoint_reads_the_evidence_rather_than_being_told_about_it(plane: Any) -> None:
    task, session = _start(plane)
    _edit(plane)
    work.verify(plane, task["id"], session)

    result = work.checkpoint(plane, task["id"], session, reason="handoff")

    context = result["context"]
    assert sorted(context["tests_run"]) == ["static_analysis", "unit"]
    assert set(context["test_results"]) == {"PASS"}
    assert any("pytest" in command for command in context["commands_run"])
    # With nothing said by the agent, what the records prove is what the checkpoint claims.
    assert sorted(context["completed_work"]) == ["static_analysis verified", "unit verified"]


def test_a_blocked_checkpoint_may_say_that_nothing_is_proven_yet(plane: Any) -> None:
    task, session = _start(plane)

    result = work.checkpoint(plane, task["id"], session, reason="blocked")

    assert result["context"]["completed_work"] == ["no verified work yet"]
    assert result["context"]["next_action"] == f"prove: {REQUEST}"


def test_only_a_known_reason_is_recorded(plane: Any) -> None:
    task, session = _start(plane)

    with pytest.raises(ControlError, match="Unknown reason"):
        work.checkpoint(plane, task["id"], session, reason="because-i-said-so")

    assert work.CHECKPOINT_REASONS == (
        "slice_complete",
        "before_risky_operation",
        "before_release",
        "blocked",
        "context_limit",
        "handoff",
        "before_integration",
    )


def test_verification_runs_what_the_task_declared_and_records_it(plane: Any) -> None:
    task, session = _start(plane)
    _edit(plane)

    result = work.verify(plane, task["id"], session)

    assert result["status"] == "PASS"
    assert result["outstanding"] == []
    recorded = [
        record for record in plane.store.list("evidence") if record["task_id"] == task["id"]
    ]
    assert {record["kind"] for record in recorded} == {"unit", "static_analysis"}
    assert {record["result"] for record in recorded} == {"PASS"}


def test_finishing_verifies_checkpoints_and_completes_without_being_asked(plane: Any) -> None:
    task, session = _start(plane)
    _edit(plane)

    result = work.finish(plane, task["id"], session)

    assert (result["status"], result["state"]) == ("PASS", "COMPLETED")
    assert result["reason"] == "every requirement of completion is met"
    assert result["outstanding"] == []
    # A checkpoint was taken before integration, and the verification ran on the way.
    checkpoints = [
        record["payload"]
        for record in plane.store.list("checkpoint")
        if record["task_id"] == task["id"]
    ]
    assert [item["next_action"] for item in checkpoints] == ["complete the task"]
    assert result["verification"]["status"] == "PASS"


def test_a_failing_gate_stops_completion_and_says_which(plane: Any) -> None:
    task, session = _start(plane)
    (Path(plane.root) / "src" / "app.py").write_text("VALUE = 1\nTOTAL =\n", encoding="utf-8")

    result = work.finish(plane, task["id"], session)

    assert (result["status"], result["code"]) == ("BLOCKED", "VERIFICATION_FAILED")
    assert result["reason"] == "verification did not pass, so the task cannot complete"
    assert result["completion"] is None
    assert plane.store.get(task["id"], "task")["state"] != "COMPLETED"
    failed = [
        record["kind"]
        for record in plane.store.list("evidence")
        if record["task_id"] == task["id"] and record["result"] != "PASS"
    ]
    assert failed


def test_evidence_that_went_stale_after_verification_blocks_completion(plane: Any) -> None:
    """The 2.1 invariant, reached through the automatic path: a proof counts only while the
    inputs it was taken against are still the inputs. Editing the work after it was verified
    leaves a claim without current evidence, and completion refuses rather than trusting the
    earlier run."""

    task, session = _start(plane)
    _edit(plane)
    assert work.verify(plane, task["id"], session)["status"] == "PASS"
    (Path(plane.root) / "src" / "app.py").write_text("VALUE = 1\nTOTAL = 3\n", encoding="utf-8")

    result = work.finish(plane, task["id"], session)

    assert result["status"] == "BLOCKED"
    assert result["outstanding"] == [REQUEST]
    assert plane.store.get(task["id"], "task")["state"] != "COMPLETED"


def test_the_next_ready_task_is_offered_when_one_finishes(plane: Any) -> None:
    first_task, session = _start(plane)
    second = work.start(plane, "Add a subtotal to tests/test_app.py")
    assert second["state"] == "WAITING"

    _edit(plane)
    assert work.finish(plane, first_task["id"], session)["status"] == "PASS"

    following = work.next_ready(plane)
    assert following is not None
    assert following["id"] == second["task"]["id"]


def test_nothing_is_offered_when_no_task_is_ready(plane: Any) -> None:
    task, session = _start(plane)
    assert work.next_ready(plane) is None
    _edit(plane)
    work.finish(plane, task["id"], session)
    assert work.next_ready(plane) is None


def test_the_automatic_path_is_on_the_api_beside_the_explicit_operations(plane: Any) -> None:
    from agentic_discipline.control.api import LOCAL_ONLY, READ_ONLY, SCHEMAS, call

    assert {"work_checkpoint", "work_verify", "work_finish"} <= set(SCHEMAS)
    # A session-bearing operation is the worker's, the way `checkpoint_task` and `verify` are.
    assert not {"work_checkpoint", "work_verify", "work_finish"} & LOCAL_ONLY
    assert "work_next" in READ_ONLY
    # And the hand-written path is still there for anyone who wants it.
    assert "checkpoint_task" in SCHEMAS

    task, session = _start(plane)
    _edit(plane)
    answer = call(
        plane,
        "work_checkpoint",
        {"task_id": task["id"], "session": session, "reason": "slice_complete"},
    )
    assert answer["data"]["status"] == "PASS"
    finished = call(plane, "work_finish", {"task_id": task["id"], "session": session})
    assert finished["data"]["state"] == "COMPLETED"


def test_a_run_artifact_is_not_a_change_outside_the_scope(plane: Any) -> None:
    """Running the project's own coverage gate wrote `.coverage` into the tree, which counted
    as a change outside the task's scope and failed the task for a file nobody wrote."""

    from agentic_discipline.control.discovery import allowed
    from agentic_discipline.control.verification import changed_paths

    task, session = _start(plane)
    _edit(plane)
    (Path(plane.root) / ".coverage").write_bytes(b"binary coverage data")
    (Path(plane.root) / ".coverage.host.1234").write_bytes(b"parallel run data")

    assert not allowed(Path(".coverage"))
    assert not allowed(Path(".coverage.host.1234"))
    assert changed_paths(plane, plane.store.get(task["id"], "task")) == ["src/app.py"]
    assert work.finish(plane, task["id"], session)["status"] == "PASS"
