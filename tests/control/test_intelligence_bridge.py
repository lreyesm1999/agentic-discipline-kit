import hashlib
import json
from pathlib import Path

import pytest
from conftest import contract

from agentic_discipline.control.intelligence import intelligence_snapshot
from agentic_discipline.control.verification import binding


def _write_handoff(project, task, *, blockers=None, items=None, constraints=None):
    directory = project.root / ".agentic" / "intelligence"
    directory.mkdir(exist_ok=True)
    (directory / "readiness.json").write_text(json.dumps({
        "ready": not blockers, "blockers": blockers or [],
    }), encoding="utf-8")
    (directory / "latest-context.json").write_text(json.dumps({
        "root_id": task, "items": [{"node": {"id": item}} for item in (items or [])],
    }), encoding="utf-8")
    (directory / "executable-constraints.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in (constraints or [])), encoding="utf-8",
    )
    return directory


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


def test_intelligence_is_optional_until_handoff_directory_exists(project):
    task = project.create_task(contract())["id"]
    assert intelligence_snapshot(project.root, task) == {"reasons": [], "constraints": [], "binding": None}


def test_intelligence_blockers_and_constraints_are_task_scoped(project):
    task_a = project.create_task(contract())["id"]
    task_b = project.create_task(contract())["id"]
    _write_handoff(project, task_a, blockers=[
        {"code": "research_gate_missing", "id": task_a},
        {"code": "blocking_assumption", "id": "CON-A"},
        {"code": "unrelated", "id": task_b},
        {"code": "unrelated_node", "id": "CON-OTHER"},
    ], items=["CON-A"], constraints=[
        {"id": "CON-A", "severity": "mandatory", "normative": False},
        {"id": "CON-OTHER", "severity": "mandatory", "normative": False},
    ])
    a = intelligence_snapshot(project.root, task_a)
    assert {reason.get("code") for reason in a["reasons"]} >= {
        "research_gate_missing", "blocking_assumption",
    }
    assert not any(reason.get("code") == "unrelated" for reason in a["reasons"])
    assert [row["id"] for row in a["constraints"]] == ["CON-A"]
    b = intelligence_snapshot(project.root, task_b)
    assert b["reasons"] == [{"type": "intelligence_invalid",
                             "detail": "Handoff context belongs to a different task"}]
    assert b["constraints"] == []


@pytest.mark.parametrize(("artifact", "contents"), [
    ("readiness.json", "[]"),
    ("readiness.json", '{"ready": true}'),
    ("readiness.json", '{"blockers": "wrong"}'),
    ("readiness.json", "not json"),
    ("latest-context.json", "[]"),
    ("latest-context.json", '{"root_id": "TASK", "items": "wrong"}'),
    ("latest-context.json", "not json"),
    ("executable-constraints.jsonl", "not json\n"),
    ("executable-constraints.jsonl", "[]\n"),
    ("executable-constraints.jsonl", '{"severity": "mandatory"}\n'),
])
def test_invalid_intelligence_artifacts_block_execution(project, artifact, contents):
    task = project.create_task(contract())["id"]
    directory = _write_handoff(project, task, items=["CON-1"])
    (directory / artifact).write_text(contents, encoding="utf-8")
    assert any(reason["type"] == "intelligence_invalid"
               for reason in project.readiness(task)["reasons"])


def test_oversized_intelligence_artifact_blocks_execution(project):
    task = project.create_task(contract())["id"]
    directory = _write_handoff(project, task)
    (directory / "readiness.json").write_text(" " * 2_000_001, encoding="utf-8")
    assert {reason.get("detail") for reason in project.readiness(task)["reasons"]
            if reason["type"] == "intelligence_invalid"} == {
                "Invalid handoff artifact: readiness.json",
            }


def test_invalid_handoff_directory_has_actionable_detail(project):
    task = project.create_task(contract())["id"]
    directory = project.root / ".agentic" / "intelligence"
    directory.write_text("not a directory", encoding="utf-8")
    assert intelligence_snapshot(project.root, task)["reasons"] == [{
        "type": "intelligence_invalid", "detail": "handoff directory",
    }]


@pytest.mark.parametrize(("artifact", "contents", "detail"), [
    ("readiness.json", "[]", "Invalid readiness report"),
    ("latest-context.json", "[]", "Invalid task context"),
    ("executable-constraints.jsonl", "[]\n", "Invalid executable constraint row"),
])
def test_invalid_handoff_reports_source_of_error(project, artifact, contents, detail):
    task = project.create_task(contract())["id"]
    directory = _write_handoff(project, task, items=["CON-1"])
    (directory / artifact).write_text(contents, encoding="utf-8")
    assert intelligence_snapshot(project.root, task)["reasons"] == [{
        "type": "intelligence_invalid", "detail": detail,
    }]


def test_handoff_preserves_blocker_fields_and_ignores_malformed_context_items(project):
    task = project.create_task(contract())["id"]
    _write_handoff(project, task, blockers=[
        {"code": "research_gate_missing", "id": task},
        {"code": "unapproved_constraint", "id": "CON-A,CON-B"},
        {"code": "different", "id": "CON-Z"},
    ], items=["CON-B"], constraints=[
        {"id": "CON-B", "severity": "mandatory", "normative": False},
    ])
    directory = project.root / ".agentic" / "intelligence"
    context = json.loads((directory / "latest-context.json").read_text(encoding="utf-8"))
    context["items"].append("malformed")
    (directory / "latest-context.json").write_text(json.dumps(context), encoding="utf-8")
    snapshot = intelligence_snapshot(project.root, task)
    assert snapshot["reasons"] == [
        {"type": "intelligence_blocker", "code": "research_gate_missing", "id": task},
        {"type": "intelligence_blocker", "code": "unapproved_constraint", "id": "CON-A,CON-B"},
        {"type": "intelligence_constraint_unapproved", "id": "CON-B"},
    ]
    expected = {"reasons": snapshot["reasons"], "constraints": snapshot["constraints"]}
    assert snapshot["binding"] == hashlib.sha256(
        json.dumps(expected, sort_keys=True).encode(),
    ).hexdigest()


@pytest.mark.parametrize("blockers", [
    ["malformed"], [{"code": "missing_id"}], [{"id": "CON-1"}],
    [{"code": "wrong_id", "id": 10}],
])
def test_malformed_readiness_blockers_fail_closed(project, blockers):
    task = project.create_task(contract())["id"]
    _write_handoff(project, task, blockers=blockers)
    assert intelligence_snapshot(project.root, task)["reasons"] == [{
        "type": "intelligence_invalid", "detail": "Invalid readiness blocker",
    }]


def test_task_blocker_is_not_duplicated_when_task_is_in_context(project):
    task = project.create_task(contract())["id"]
    _write_handoff(project, task, blockers=[{"code": "task_gap", "id": task}], items=[task])
    assert intelligence_snapshot(project.root, task)["reasons"] == [{
        "type": "intelligence_blocker", "code": "task_gap", "id": task,
    }]


def test_blank_constraint_rows_do_not_hide_later_rules(project):
    task = project.create_task(contract())["id"]
    directory = _write_handoff(project, task, items=["CON-1"])
    (directory / "executable-constraints.jsonl").write_text(
        "\n" + json.dumps({"id": "CON-1", "severity": "mandatory", "normative": False}) + "\n",
        encoding="utf-8",
    )
    assert [reason["id"] for reason in intelligence_snapshot(project.root, task)["reasons"]] == [
        "CON-1",
    ]


def test_handoff_reads_json_with_explicit_utf8(project, monkeypatch):
    task = project.create_task(contract())["id"]
    _write_handoff(project, task)
    original = Path.read_text
    seen = []

    def read_text(path, *args, **kwargs):
        if path.parent.name == "intelligence":
            seen.append(kwargs.get("encoding"))
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)
    assert intelligence_snapshot(project.root, task)["reasons"] == []
    assert seen == ["utf-8", "utf-8", "utf-8"]


@pytest.mark.parametrize("artifact", ["readiness.json", "executable-constraints.jsonl"])
def test_handoff_rejects_artifact_symlinks(project, artifact):
    task = project.create_task(contract())["id"]
    directory = _write_handoff(project, task)
    target = project.root / "safe-copy"
    target.write_bytes((directory / artifact).read_bytes())
    (directory / artifact).unlink()
    try:
        (directory / artifact).symlink_to(target)
    except OSError:
        pytest.skip("Symlink creation is unavailable")
    assert intelligence_snapshot(project.root, task)["reasons"] == [{
        "type": "intelligence_invalid",
        "detail": f"Invalid {'handoff artifact: readiness.json' if artifact == 'readiness.json' else 'executable constraints artifact'}",
    }]


def test_constraint_artifact_size_boundary(project):
    task = project.create_task(contract())["id"]
    directory = _write_handoff(project, task)
    path = directory / "executable-constraints.jsonl"
    path.write_text(" " * 2_000_000, encoding="utf-8")
    assert intelligence_snapshot(project.root, task)["reasons"] == []
    path.write_text(" " * 2_000_001, encoding="utf-8")
    assert intelligence_snapshot(project.root, task)["reasons"] == [{
        "type": "intelligence_invalid", "detail": "Invalid executable constraints artifact",
    }]


def test_readiness_artifact_size_boundary(project):
    task = project.create_task(contract())["id"]
    directory = _write_handoff(project, task)
    path = directory / "readiness.json"
    contents = '{"ready": true, "blockers": []}'
    path.write_text(contents + " " * (2_000_000 - len(contents)), encoding="utf-8")
    assert intelligence_snapshot(project.root, task)["reasons"] == []
    path.write_text(contents + " " * (2_000_001 - len(contents)), encoding="utf-8")
    assert intelligence_snapshot(project.root, task)["reasons"] == [{
        "type": "intelligence_invalid", "detail": "Invalid handoff artifact: readiness.json",
    }]


def test_only_applicable_mandatory_constraints_enter_snapshot(project):
    task = project.create_task(contract())["id"]
    _write_handoff(project, task, items=["CON-A", "CON-B", "CON-C"], constraints=[
        {"id": "CON-A", "severity": "mandatory", "normative": True, "rule": "one_effect"},
        {"id": "CON-B", "severity": "recommended", "normative": False, "rule": "review"},
        {"id": "CON-C", "severity": "mandatory", "normative": False, "rule": "audit"},
        {"id": "CON-D", "severity": "mandatory", "normative": False, "rule": "unrelated"},
    ])
    snapshot = intelligence_snapshot(project.root, task)
    assert [row["id"] for row in snapshot["constraints"]] == ["CON-A", "CON-C"]
    assert [reason["id"] for reason in snapshot["reasons"]] == ["CON-C"]


def test_acceptance_requires_exact_mandatory_constraint_id(project):
    task = project.create_task(contract())["id"]
    _write_handoff(project, task, items=["CON-1"], constraints=[
        {"id": "CON-1", "severity": "mandatory", "normative": True},
    ])
    current = project.store.get(task, "task")
    with project.store.transaction():
        project.store.put("task", {**current, "acceptance": ["CON-10: prove other behavior"]},
                          expected=current["version"])
    assert any(reason["type"] == "intelligence_constraint_unmapped"
               for reason in project.readiness(task)["reasons"])
    current = project.store.get(task, "task")
    with project.store.transaction():
        project.store.put("task", {**current, "acceptance": ["CON-1: prove the behavior"]},
                          expected=current["version"])
    assert not any(reason["type"] == "intelligence_constraint_unmapped"
                   for reason in project.readiness(task)["reasons"])
