"""Generated files, command output and error messages, pinned exactly.

Mutation testing found each of these observable results unchecked: frontmatter for
disciplines that are not always on, the managed region of a shared file, extra
profile files, the shape of printed JSON and paths, the base a protected-path check
compares with, CRAP scores between the extremes, the text of refusals, the baseline
gate that init adds, metric extraction after a missing path, the quality report's
project name, requirement graphs and sensitivity evidence of the wrong type, and the
names Python symbols are recorded under.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline import cli, profiles
from agentic_discipline.adapters import MANAGED_END, MANAGED_START, Emission, sync_adapters
from agentic_discipline.bootstrap import find_contract_root, initialize_project
from agentic_discipline.common import AgenticError
from agentic_discipline.control.discovery import python_symbols
from agentic_discipline.crap import crap_score
from agentic_discipline.evidence import append_evidence
from agentic_discipline.evolution import register_lifecycle
from agentic_discipline.profiles import (
    BASELINE_GATE,
    Detection,
    Profile,
    annotate_gate_availability,
    build_quality_config,
    load_profiles,
    requested_projects,
)
from agentic_discipline.quality import extract_metrics
from agentic_discipline.requirements import validate_requirement_graph
from agentic_discipline.skills import load_disciplines, parse_frontmatter
from agentic_discipline.validation import validate_quality_config, validate_schema
from agentic_discipline.verifier.protection import protect_verifier
from agentic_discipline.verifier.registry import register_verifier
from agentic_discipline.verifier.schema import load_and_validate_verifier, validate_verifier
from agentic_discipline.verifier.sensitivity import sensitivity_status


@pytest.fixture
def printed(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    output: list[Any] = []
    monkeypatch.setattr(cli, "_json", output.append)
    return output


# --- adapters -------------------------------------------------------------------------------


def _optional_discipline() -> Any:
    return next(d for d in load_disciplines(find_contract_root()) if not d.always)


def test_a_discipline_that_is_not_always_on_is_scoped_by_its_globs(tmp_path: Path) -> None:
    item = _optional_discipline()
    sync_adapters(tmp_path, ["cursor", "windsurf"])

    cursor, _ = parse_frontmatter(
        (tmp_path / ".cursor" / "rules" / f"agentic-{item.id}.mdc").read_text(encoding="utf-8"),
        "cursor",
    )
    windsurf, _ = parse_frontmatter(
        (tmp_path / ".windsurf" / "rules" / f"agentic-{item.id}.md").read_text(encoding="utf-8"),
        "windsurf",
    )

    assert cursor["alwaysApply"] == "false"
    assert windsurf["trigger"] == "glob"


def test_frontmatter_and_document_are_separated_by_one_newline(tmp_path: Path) -> None:
    item = _optional_discipline()
    sync_adapters(tmp_path, ["claude"])

    text = (tmp_path / ".claude" / "skills" / f"agentic-{item.id}" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "\n---\n\n" in text
    assert "XX" not in text


def test_the_managed_region_replaced_is_the_first_complete_one(tmp_path: Path) -> None:
    path = tmp_path / "AGENTS.md"
    first = f"{MANAGED_START}\nold one\n{MANAGED_END}"
    second = f"{MANAGED_START}\nold two\n{MANAGED_END}"
    path.write_text(f"intro {MANAGED_END}\n{first}\nmiddle\n{second}\n", encoding="utf-8")

    Emission().write_managed(path, "new")

    assert path.read_text(encoding="utf-8") == (
        f"intro {MANAGED_END}\n{MANAGED_START}\n\nnew\n\n{MANAGED_END}\nmiddle\n{second}\n"
    )


# --- init and profiles ----------------------------------------------------------------------


def test_extra_profile_files_are_loaded(tmp_path: Path) -> None:
    root = find_contract_root()
    source = root / "config" / "profiles" / "generic.json"
    descriptor = json.loads(source.read_text(encoding="utf-8"))
    extra = tmp_path / "custom.json"
    extra.write_text(
        json.dumps(
            {**descriptor, "id": "custom", "config": str(source.parent / descriptor["config"])}
        ),
        encoding="utf-8",
    )

    assert "custom" in load_profiles(root, [extra])
    target = tmp_path / "project"
    result = initialize_project(target, ["custom"], profile_files=[extra], adapters=["generic"])
    assert result["profiles"] == ["custom"]


def test_an_unknown_profile_is_named_with_every_available_one(tmp_path: Path) -> None:
    known = load_profiles(find_contract_root())

    with pytest.raises(AgenticError) as caught:
        requested_projects(tmp_path, ["nope"], known)

    assert (
        str(caught.value)
        == f"profile not found: nope; available profiles: {', '.join(sorted(known))}"
    )


def test_a_broken_profile_configuration_is_named_in_the_error(tmp_path: Path) -> None:
    config = tmp_path / "quality.json"
    config.write_text("{", encoding="utf-8")
    profile = Profile(id="x", label="X", config_path=config, detectors=())
    detection = Detection(profile="x", label="X", root=tmp_path, confidence=1.0, evidence=())

    with pytest.raises(AgenticError) as caught:
        build_quality_config(tmp_path, [detection], {"x": profile})

    assert str(caught.value).startswith(f"invalid quality configuration for x at {config}: ")


def test_gates_without_a_required_flag_count_as_required(tmp_path: Path) -> None:
    config = {"gates": [{"name": "diff", "command": ["git", "diff", "--check"]}]}

    assert annotate_gate_availability(tmp_path, config)["gates"] == [
        {"name": "diff", "command": ["git", "diff", "--check"]}
    ]


def test_the_baseline_gate_added_is_a_copy_the_caller_may_change(tmp_path: Path) -> None:
    original = json.loads(json.dumps(BASELINE_GATE))
    config = {"gates": [{"name": "t", "command": ["definitely-missing-tool-xyz"]}]}

    gates = annotate_gate_availability(tmp_path, config)["gates"]
    gates[-1]["command"].append("--changed")

    assert profiles.BASELINE_GATE == original


# --- CLI output -----------------------------------------------------------------------------


def test_json_output_is_indented_by_two_spaces(capsys: pytest.CaptureFixture[str]) -> None:
    cli._json({"status": "PASS"})
    assert capsys.readouterr().out == '{\n  "status": "PASS"\n}\n'


def test_rendered_paths_keep_their_spaces(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    path = tmp_path / "my rules" / "a.md"
    result = {"actions": [f"WRITE {path}"], "labels": [], "disciplines": []}

    cli._render_adapters(result, tmp_path)

    assert capsys.readouterr().out.splitlines()[-1] == "  WRITE  my rules/a.md"


def test_acceptance_and_sync_print_their_results(
    monkeypatch: pytest.MonkeyPatch, printed: list[Any], tmp_path: Path
) -> None:
    monkeypatch.setattr(cli, "compile_feature", lambda source, output: {"feature_id": "f"})
    monkeypatch.setattr(cli, "sync_adapters", lambda root, adapters, dry_run: {"synced": True})

    cli.command_acceptance(argparse.Namespace(input="a.feature", output="out.json"))
    cli.command_adapters_sync(
        argparse.Namespace(project_root=str(tmp_path), adapter=[], dry_run=False, json=True)
    )

    assert printed == [{"feature_id": "f"}, {"synced": True}]


def test_the_protected_check_compares_with_the_requested_base(
    monkeypatch: pytest.MonkeyPatch, printed: list[Any]
) -> None:
    bases: list[str] = []
    monkeypatch.setattr(cli, "changed_files", lambda base: bases.append(base) or [])

    cli.command_protected(argparse.Namespace(base_ref="origin/release"))

    assert bases == ["origin/release"]


# --- scores, messages and parsers -----------------------------------------------------------


def test_crap_score_between_no_and_full_coverage() -> None:
    assert crap_score(10, 50) == 10**2 * 0.5**3 + 10


def test_appending_to_a_broken_ledger_names_every_error(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(json.dumps({"sequence": 7}) + "\n" + json.dumps({}) + "\n", encoding="utf-8")
    artifact = tmp_path / "a.json"
    artifact.write_text("{}", encoding="utf-8")

    with pytest.raises(AgenticError) as caught:
        append_evidence(ledger, artifact, tool="t", command="c", exit_code=0)

    message = str(caught.value)
    assert message.startswith("refusing to append to an invalid evidence ledger: record 1: ")
    assert "; record 2: " in message


def test_an_incomplete_lifecycle_item_is_refused_with_its_reason(tmp_path: Path) -> None:
    with pytest.raises(AgenticError) as caught:
        register_lifecycle(tmp_path, {"id": "TMP-1"})
    assert str(caught.value) == "lifecycle item requires id, path, and state"


def test_metrics_after_a_missing_path_are_still_read() -> None:
    parser = {"type": "json", "metrics": {"missing": "a.b", "lines": "totals.lines"}}
    assert extract_metrics('{"totals": {"lines": 91}}', parser) == {"lines": 91}


def test_a_graph_whose_edges_are_not_a_list_stops_at_the_schema(tmp_path: Path) -> None:
    graph: dict[str, Any] = {"feature_id": "F", "nodes": [], "edges": {"from": "x"}}

    assert validate_requirement_graph(graph) == validate_schema(
        graph, "requirement-graph.schema.json"
    )


def test_dependencies_do_not_count_as_traceability_to_evidence() -> None:
    graph = {
        "feature_id": "F",
        "nodes": [
            {"id": "FR-1", "type": "requirement"},
            {"id": "FR-2", "type": "requirement"},
            {"id": "EV-1", "type": "evidence"},
        ],
        "edges": [
            {"from": "FR-1", "to": "FR-2", "relation": "depends_on"},
            {"from": "FR-2", "to": "EV-1", "relation": "evidenced_by"},
        ],
    }

    errors = validate_requirement_graph(graph, complete=True)

    # FR-2 is traced to evidence; depending on it does not trace FR-1.
    assert "requirements.FR-1: no traceability path reaches evidence" in errors
    assert "requirements.FR-2: no traceability path reaches evidence" not in errors


def test_a_configuration_with_no_required_gate_says_so() -> None:
    config = {"project": "x", "gates": [{"name": "t", "command": ["t"], "required": False}]}
    assert "gates: at least one gate must be required" in validate_quality_config(config)


def test_python_symbols_keep_their_nesting_and_relative_imports() -> None:
    tree = ast.parse(
        "from . import sibling\n"
        "if True:\n"
        "    def guarded():\n"
        "        pass\n"
        "class Box:\n"
        "    if True:\n"
        "        def inner(self):\n"
        "            pass\n"
    )

    names = [(s["name"], s["type"]) for s in python_symbols(tree)]

    assert names == [
        ("", "Import"),
        ("guarded", "FunctionDef"),
        ("Box", "ClassDef"),
        ("Box.inner", "FunctionDef"),
    ]


# --- verifiers ------------------------------------------------------------------------------


def _contract(directory: Path, **changes: Any) -> Path:
    directory.mkdir()
    contract = {
        "schema_version": "1",
        "id": "VER-MSG",
        "name": "messages",
        "requirement_ids": ["REQ-1"],
        "claim": "messages are exact",
        "type": "custom",
        "origin": "handwritten",
        "risk": "LOW",
        "command": ["python", "run.py"],
        "timeout_seconds": 10,
        "working_directory": ".",
        "expected_exit_code": 0,
        "sensitivity": {"method": "negative_control", "status": "UNPROVEN"},
        "persistence": "durable",
        "protected": False,
        **changes,
    }
    (directory / "verifier.json").write_text(json.dumps(contract), encoding="utf-8")
    (directory / "run.py").write_text("pass\n", encoding="utf-8")
    return directory


def test_an_unproven_verifier_cannot_be_protected(tmp_path: Path) -> None:
    project = tmp_path / "project"
    initialize_project(project, adapters=["generic"])
    register_verifier(_contract(tmp_path / "source"), project)

    with pytest.raises(AgenticError) as caught:
        protect_verifier(project, "VER-MSG")

    assert str(caught.value) == "only sensitivity-validated verifiers can be protected"


def test_every_verifier_contract_error_is_reported(tmp_path: Path) -> None:
    directory = _contract(tmp_path / "bad", risk="EXTREME", timeout_seconds=-1)

    with pytest.raises(AgenticError) as caught:
        load_and_validate_verifier(directory / "verifier.json")

    errors = validate_verifier(json.loads((directory / "verifier.json").read_text("utf-8")))
    assert len(errors) > 1
    assert str(caught.value) == "invalid verifier contract: " + "; ".join(errors)


def test_sensitivity_evidence_that_is_not_text_is_refused(tmp_path: Path) -> None:
    metadata = {"sensitivity": {"status": "PROVEN", "evidence": 5}}

    with pytest.raises(AgenticError) as caught:
        sensitivity_status(metadata, tmp_path, tmp_path)

    assert str(caught.value) == "validated verifier is missing sensitivity evidence"


# --- documents missing an optional key ------------------------------------------------------


def test_a_scenario_without_steps_is_reported_not_crashed_on() -> None:
    from agentic_discipline.acceptance import validate_acceptance_ir

    ir = {"feature_id": "F", "scenarios": [{"id": "AC-001", "requirements": ["FR-1"]}]}

    errors = validate_acceptance_ir(ir)

    assert errors and any("steps" in error for error in errors)


def test_a_profile_without_detectors_loads_with_none(tmp_path: Path) -> None:
    from agentic_discipline.profiles import load_profile

    root = find_contract_root() / "config" / "profiles"
    descriptor = json.loads((root / "generic.json").read_text(encoding="utf-8"))
    descriptor.pop("detectors", None)
    descriptor["config"] = str(
        root / json.loads((root / "generic.json").read_text("utf-8"))["config"]
    )
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(descriptor), encoding="utf-8")

    assert load_profile(path).detectors == ()


def test_a_parser_without_metrics_extracts_and_validates_to_nothing() -> None:
    assert extract_metrics("lines 10", {"type": "regex"}) == {}
    config = {
        "project": "x",
        "gates": [{"name": "t", "command": ["t"], "parser": {"type": "json"}}],
    }
    assert isinstance(validate_quality_config(config), list)


def test_a_graph_without_edges_is_still_checked_for_traceability() -> None:
    graph = {"feature_id": "F", "nodes": [{"id": "FR-1", "type": "requirement"}]}

    errors = validate_requirement_graph(graph, complete=True)

    assert "requirements.FR-1: no traceability path reaches evidence" in errors


def test_a_verifier_contract_without_sensitivity_is_reported_not_crashed_on() -> None:
    errors = validate_verifier({"id": "VER-X", "protected": True})
    assert errors
