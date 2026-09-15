"""The task context document, section by section.

``Plane.context`` is what an agent receives before working on a task: mandatory
knowledge it must not lose, optional source entities within a byte budget, and an
audit of that budget. Existing tests read one or two fields, so sections could be
dropped, filtered wrongly or mis-measured without a failure. The scenario puts both
included and excluded items next to each other in every section.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from conftest import checkpoint, contract
from test_kernel import entity

from agentic_discipline.control.contracts import ControlError, encode
from agentic_discipline.control.verification import verify

HIDDEN_TASK_FIELDS = {"initial_files", "initial_links", "initial_line_counts", "integration"}


def _force(project: Any, kind: str, identifier: str, **fields: Any) -> dict[str, Any]:
    with project.store.transaction():
        current = project.store.get(identifier, kind)
        return project.store.put(kind, {**current, **fields}, expected=current["version"])


def _size(item: Any) -> int:
    return len(encode(item).encode())


def _scenario(project: Any) -> dict[str, Any]:
    # A code entity outside the task scope, which must never become a source.
    (project.root / "docs").mkdir()
    (project.root / "docs" / "notes.py").write_text("note = 1\n")
    project.reconcile()

    requirement, human_decision, architecture, weak_decision, human_code = project.knowledge.apply(
        [
            entity("Orders"),
            {**entity("Keep local data"), "graph": "decision", "authority": "human"},
            {**entity("Layering"), "graph": "architecture", "authority": "contract"},
            {**entity("Maybe cache"), "graph": "decision", "authority": "documentation"},
            {**entity("Style guide"), "graph": "code", "authority": "human", "source_ref": "x"},
        ],
        project.store.knowledge_version,
        "context scenario",
    )["entities"]

    project.approve_command(contract()["verification"][0]["command"])
    task = project.create_task(
        {
            **contract(),
            "requirements": [requirement["id"]],
            "context": [requirement["id"], "app.py"],
        }
    )["id"]
    other = project.create_task(contract())["id"]
    session = project.join("worker", ["code", "terminal"])["session"]

    # A decision recorded for this task, and one recorded for another task.
    project.ready(task)
    project.claim(task, session)
    project.release(task, session, "Choose a retention period")
    project.resolve_blocker(task, "Thirty days")
    _force(project, "task", other, state="BLOCKED", blocker="Choose an archive format")
    project.resolve_blocker(other, "Parquet")

    project.ready(task)
    project.claim(task, session)
    project.checkpoint(task, session, checkpoint())
    latest = project.checkpoint(task, session, {**checkpoint(), "next_action": "Fix the value"})

    assert verify(project, task, session)["status"] == "PASS"
    (project.root / "app.py").write_text("value = 0\n")
    failure = verify(project, task, session)["evidence"][0]
    assert failure["result"] == "FAIL"

    _force(
        project,
        "task",
        task,
        integration={
            "status": "PASS",
            "binding": "reviewed",
            "merge_performed": False,
            "merged_files": {"app.py": "hash"},
        },
    )
    return {
        "task": task,
        "requirement": requirement["id"],
        "protected": {human_decision["id"], architecture["id"]},
        "unprotected": {weak_decision["id"], human_code["id"]},
        "checkpoint": latest["id"],
        "failure": failure["id"],
    }


def _expected_sources(project: Any, task: dict[str, Any], used: int, budget: int) -> list[Any]:
    sources = []
    for item in project.store.list("entity"):
        in_scope = any(
            scope == "."
            or item["source_ref"] == scope
            or item["source_ref"].startswith(scope.rstrip("/") + "/")
            for scope in task["scope"]
        )
        if item["lifecycle"] == "ACTIVE" and not item.get("stale") and item["graph"] == "code":
            if in_scope and used + _size(item) <= budget:
                sources.append(item)
                used += _size(item)
    return sources


def test_context_mandatory_sections_keep_what_the_agent_needs(project: Any) -> None:
    ids = _scenario(project)
    store = project.store
    task = store.get(ids["task"], "task")
    active = [e for e in store.list("entity") if e["lifecycle"] == "ACTIVE" and not e.get("stale")]

    context = project.context(ids["task"])
    mandatory = context["mandatory"]

    assert list(mandatory) == [
        "task",
        "integration",
        "requirements",
        "required_context",
        "protected_decisions",
        "decisions",
        "checkpoint",
        "policy",
        "current_failures",
    ]
    assert HIDDEN_TASK_FIELDS <= task.keys()
    assert mandatory["task"] == {k: v for k, v in task.items() if k not in HIDDEN_TASK_FIELDS}
    assert mandatory["integration"] == {
        "status": "PASS",
        "binding": "reviewed",
        "merge_performed": False,
    }
    assert mandatory["requirements"] == [store.get(ids["requirement"], "entity")]

    by_path = [e for e in active if e["source_ref"] == "app.py"]
    assert by_path
    assert mandatory["required_context"] == [store.get(ids["requirement"], "entity"), *by_path]

    protected = {e["id"] for e in mandatory["protected_decisions"]}
    assert protected == ids["protected"]
    assert not protected & ids["unprotected"]

    decisions = [d for d in store.list("decision") if d.get("task_id") == ids["task"]]
    assert [d["decision"] for d in decisions] == ["Thirty days"]
    assert mandatory["decisions"] == decisions
    assert mandatory["checkpoint"]["id"] == ids["checkpoint"]
    assert mandatory["checkpoint"]["payload"]["next_action"] == "Fix the value"
    assert mandatory["policy"] == project.policy()

    (failure,) = mandatory["current_failures"]
    artifact = project.directory / "evidence" / f"{ids['failure']}.json"
    assert failure["evidence"]["id"] == ids["failure"]
    assert failure["output"] == json.loads(artifact.read_text(encoding="utf-8"))
    assert failure["output"]["exit_code"] != 0


def test_context_sources_fill_the_budget_and_audit_it(project: Any) -> None:
    ids = _scenario(project)
    task = project.store.get(ids["task"], "task")
    context = project.context(ids["task"])
    mandatory_bytes = _size(context["mandatory"])

    sources = _expected_sources(project, task, mandatory_bytes, 16000)
    assert any(item["source_ref"] == "app.py" for item in sources)
    assert context["sources"] == sources
    assert not any(item["source_ref"].startswith("docs/") for item in context["sources"])
    used = mandatory_bytes + sum(_size(item) for item in sources)
    assert context["audit"] == {
        "bytes": used,
        "budget_bytes": 16000,
        "estimated_tokens": (used + 3) // 4,
        "mandatory_bytes": mandatory_bytes,
        "estimate_only": True,
    }
    assert context["source_confirmation_required"] is True

    # A budget that fits the mandatory part and exactly the first source.
    first = sources[0]
    budget = mandatory_bytes + _size(first)
    tight = project.context(ids["task"], budget=budget)
    assert tight["sources"] == [first]
    assert tight["audit"]["bytes"] == budget
    assert tight["audit"]["estimated_tokens"] == (budget + 3) // 4


def test_retired_and_stale_decisions_are_not_protected(project: Any) -> None:
    kept, retired, stale = project.knowledge.apply(
        [
            {**entity(name), "graph": "decision", "authority": "human"}
            for name in ("Keep local data", "Old retention", "Stale retention")
        ],
        project.store.knowledge_version,
        "decisions",
    )["entities"]
    project.knowledge.lifecycle(retired["id"], "RETIRED", "replaced")
    _force(project, "entity", stale["id"], stale=True)
    project.approve_command(contract()["verification"][0]["command"])
    task = project.create_task(contract())["id"]

    protected = project.context(task)["mandatory"]["protected_decisions"]
    assert [item["id"] for item in protected] == [kept["id"]]


def test_stale_requirement_blocks_the_context(project: Any) -> None:
    (requirement,) = project.knowledge.apply(
        [entity("Orders")], project.store.knowledge_version, "requirement"
    )["entities"]
    project.approve_command(contract()["verification"][0]["command"])
    task = project.create_task({**contract(), "requirements": [requirement["id"]]})["id"]
    _force(project, "entity", requirement["id"], stale=True)

    with pytest.raises(ControlError) as caught:
        project.context(task)
    assert (caught.value.code, str(caught.value)) == (
        "STALE_CONTEXT",
        "Required knowledge is not current",
    )


def test_latest_passing_run_clears_current_failures(project: Any) -> None:
    project.approve_command(contract()["verification"][0]["command"])
    task = project.create_task(contract())["id"]
    project.ready(task)
    session = project.join("worker", ["code", "terminal"])["session"]
    project.claim(task, session)
    (project.root / "app.py").write_text("value = 0\n")
    assert verify(project, task, session)["status"] == "FAIL"
    assert project.context(task)["mandatory"]["current_failures"]

    (project.root / "app.py").write_text("value = 1\n")
    assert verify(project, task, session)["status"] == "PASS"
    assert project.context(task)["mandatory"]["current_failures"] == []


def test_whole_repository_scope_offers_every_code_source(project: Any) -> None:
    (project.root / "docs").mkdir()
    (project.root / "docs" / "notes.py").write_text("note = 1\n")
    project.reconcile()
    project.approve_command(contract()["verification"][0]["command"])
    task = project.create_task({**contract(), "scope": ["."]})["id"]

    refs = {item["source_ref"] for item in project.context(task, budget=1_000_000)["sources"]}
    assert {"app.py", "docs/notes.py"} <= refs

    # A directory scope offers the code inside it and nothing outside it.
    directory = project.create_task({**contract(), "scope": ["docs"]})["id"]
    inside = {item["source_ref"] for item in project.context(directory)["sources"]}
    assert "docs/notes.py" in inside
    assert "app.py" not in inside


def test_budget_equal_to_the_mandatory_part_is_allowed(project: Any) -> None:
    project.approve_command(contract()["verification"][0]["command"])
    # Pad the objective until the mandatory part is a multiple of four bytes, where
    # rounding the token estimate up and down give different answers. Padding one
    # task keeps its ids and timestamps, so each step adds exactly one byte and four
    # steps always reach a multiple of four; separate tasks vary in timestamp length.
    task = project.create_task(contract())
    for padding in range(4):
        task = _force(project, "task", task["id"], objective="Verify value" + "!" * padding)
        mandatory = project.context(task["id"])["audit"]["mandatory_bytes"]
        if mandatory % 4 == 0:
            break
    else:
        pytest.fail("no padding produced a mandatory size divisible by four")

    exact = project.context(task["id"], budget=mandatory)
    assert exact["sources"] == []
    assert exact["audit"]["bytes"] == mandatory
    assert exact["audit"]["estimated_tokens"] == mandatory // 4
