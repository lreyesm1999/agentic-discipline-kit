import json

from conftest import contract

from agentic_discipline.control.intelligence import intelligence_snapshot
from agentic_discipline.control.verification import binding


def test_intelligence_research_and_mandatory_constraint_gate(project):
    task = project.create_task(contract())["id"]
    handoff = project.root / ".agentic" / "intelligence"
    handoff.mkdir()
    (handoff / "readiness.json").write_text(json.dumps({
        "ready": False,
        "blockers": [{"code": "research_gate_missing", "id": task, "kind": "official_standard"},
                     {"code": "blocked", "id": "CON-1"}],
    }), encoding="utf-8")
    (handoff / "latest-context.json").write_text(json.dumps({
        "root_id": task, "items": [{"node": {"id": "CON-1"}}],
    }), encoding="utf-8")
    constraint = {"id": "CON-1", "severity": "mandatory", "normative": False,
                  "rule": "callbacks_are_idempotent", "verification": "automated_test_required"}
    (handoff / "executable-constraints.jsonl").write_text(json.dumps(constraint) + "\n",
                                                             encoding="utf-8")
    reasons = project.readiness(task)["reasons"]
    assert any(reason.get("code") == "research_gate_missing" for reason in reasons)
    assert any(reason.get("code") == "blocked" for reason in reasons)
    assert any(reason["type"] == "intelligence_constraint_unapproved" for reason in reasons)
    before = intelligence_snapshot(project.root, task)["binding"]
    proof_before = binding(project, project.store.get(task, "task"))["intelligence"]
    constraint["normative"] = True
    (handoff / "executable-constraints.jsonl").write_text(json.dumps(constraint) + "\n",
                                                             encoding="utf-8")
    assert intelligence_snapshot(project.root, task)["binding"] != before
    assert binding(project, project.store.get(task, "task"))["intelligence"] != proof_before
    assert any(reason.get("code") == "research_gate_missing" for reason in project.readiness(task)["reasons"])
    assert any(reason["type"] == "intelligence_constraint_unmapped" for reason in project.readiness(task)["reasons"])
    current = project.store.get(task, "task")
    with project.store.transaction():
        project.store.put("task", {**current, "acceptance": ["CON-1: callbacks are idempotent"]},
                          expected=current["version"])
    assert not any(reason["type"] == "intelligence_constraint_unmapped"
                   for reason in project.readiness(task)["reasons"])
    assert intelligence_snapshot(project.root, "OTHER")["constraints"] == []


def test_incomplete_intelligence_handoff_fails_closed(project):
    task = project.create_task(contract())["id"]
    handoff = project.root / ".agentic" / "intelligence"
    handoff.mkdir()
    assert any(reason["type"] == "intelligence_invalid" for reason in project.readiness(task)["reasons"])
    (handoff / "readiness.json").write_text(json.dumps({"ready": True, "blockers": []}),
                                              encoding="utf-8")
    assert any(reason["type"] == "intelligence_invalid" for reason in project.readiness(task)["reasons"])
