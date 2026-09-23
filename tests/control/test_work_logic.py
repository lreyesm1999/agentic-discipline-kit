"""The small decisions work derivation makes, each one checked on its own.

Which words of a request are worth searching for, which paths it names, which requirements
it matches and in what order, which gate is which kind of proof, which paths are protected,
which open work a new task waits for. Each of these is a rule someone can read in the code,
so each is pinned here where a change to it shows.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline.bootstrap import initialize_project
from agentic_discipline.common import run_git
from agentic_discipline.control import work
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
    (root / "src" / "other.py").write_text("OTHER = 2\n", encoding="utf-8")
    run_git(["init"], cwd=root)
    initialize_project(root)
    _write_gates(root / "agentic.config.json", [{"name": "python/tests", "command": GATE}])
    with Plane(root) as opened:
        opened.reconcile()
        yield opened


def _requirement(plane: Any, name: str, **fields: Any) -> dict[str, Any]:
    entity: dict[str, Any] = plane.knowledge.apply(
        [
            {
                "graph": "requirement",
                "type": "requirement",
                "name": name,
                "source_ref": "specs/requirements.md",
                "authority": "human",
                "confidence": 1,
                "observation": "DECLARED",
                **fields,
            }
        ],
        plane.store.knowledge_version,
        "approved requirement",
    )["entities"][0]
    return entity


def _set(plane: Any, identifier: str, kind: str, **changes: Any) -> None:
    current = plane.store.get(identifier, kind)
    with plane.store.transaction():
        plane.store.put(kind, {**current, **changes}, expected=current["version"])


# --- reading the request -------------------------------------------------------------------


def test_the_searchable_words_are_lowercased_once_each_in_order_without_filler() -> None:
    assert work.terms("Total, the TOTAL again: src/app.py.") == ["total", "again", "src/app.py"]
    assert work.terms("Fix the Total") == ["total"]
    assert work.terms("Rename src/app.py/ and .hidden.") == ["rename", "src/app.py", "hidden"]
    # Two letters are not a word worth searching for.
    assert work.terms("do it on db") == []


def test_the_same_request_in_other_spacing_and_case_is_the_same_request() -> None:
    assert work.digest("Add  a TOTAL\tto src/app.py") == work.digest("add a total to src/app.py")
    assert len(work.digest("anything")) == 16
    assert work.digest("add a total") != work.digest("add a subtotal")


def test_a_named_path_is_found_through_the_punctuation_around_it() -> None:
    known = {"src/app.py", "src/other.py"}

    assert work._paths_in("Fix src/app.py, src/other.py; and src/app.py.", known) == [
        "src/app.py",
        "src/other.py",
    ]
    assert work._paths_in("Fix src/app.py: now", known) == ["src/app.py"]
    assert work._paths_in("Fix src/missing.py", known) == []


def test_without_a_named_path_the_scope_comes_from_the_project_s_index(plane: Any) -> None:
    derived = work.derive(plane, "Fix compute_total")

    assert derived["contract"]["scope"] == ["src/app.py"]
    assert derived["provenance"]["scope_from"] == "the project's knowledge index"


def test_only_the_first_six_words_are_searched(plane: Any) -> None:
    six = "alpha bravo charlie delta echo foxtrot"

    assert work._from_knowledge(plane, f"{six} compute_total", {"src/app.py"}) == []
    assert work._from_knowledge(plane, "compute_total " + six, {"src/app.py"}) == ["src/app.py"]


def test_the_index_only_supplies_files_that_are_part_of_the_project(plane: Any) -> None:
    assert work._from_knowledge(plane, "compute_total", {"src/other.py"}) == []


# --- what the project already recorded -----------------------------------------------------


def test_requirements_are_matched_by_their_words_and_ranked_by_overlap(plane: Any) -> None:
    broad = _requirement(plane, "Totals", statement="The report shows totals")
    narrow = _requirement(plane, "Report totals", excerpt="report totals per invoice currency")
    _requirement(plane, "Unrelated", statement="Nothing in common here")

    matched = work._requirements(plane, "Report totals per invoice")

    assert [entity["id"] for entity in matched] == [narrow["id"], broad["id"]]


def test_only_active_current_requirements_are_matched(plane: Any) -> None:
    retired = _requirement(plane, "Invoice totals retired")
    stale = _requirement(plane, "Invoice totals stale")
    live = _requirement(plane, "Invoice totals live")
    _set(plane, retired["id"], "entity", lifecycle="RETIRED")
    _set(plane, stale["id"], "entity", stale=True)

    assert [e["id"] for e in work._requirements(plane, "invoice totals")] == [live["id"]]


def test_acceptance_comes_from_the_matched_requirements_skipping_blank_criteria() -> None:
    criteria, source = work._acceptance(
        "Add totals",
        [{"acceptance": ["totals add up", "  "]}, {"acceptance": ["totals are shown"]}, {}],
    )

    assert criteria == ["totals add up", "totals are shown"]
    assert source == "the acceptance criteria recorded on the matched requirements"


# --- the project's gates as verifiers ------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("mutation", "test_strength"),
        ("integration-tests", "integration"),
        ("Acceptance", "acceptance"),
        ("property", "property"),
        ("coverage", "coverage"),
        ("security", "security"),
        ("architecture", "architecture"),
        ("migrations", "migration_safety"),
        ("regression", "regression"),
        ("python/tests", "unit"),
        ("spec", "unit"),
        ("ruff", "static_analysis"),
    ],
)
def test_each_gate_name_maps_to_the_proof_it_gives(name: str, kind: str) -> None:
    assert work._kind(name) == kind


def test_the_verifiers_are_the_required_gates_in_their_own_words(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    source = Path(__file__).resolve().parents[2] / "agentic.config.example.json"
    shutil.copyfile(source, root / "agentic.config.example.json")
    _write_gates(
        root / "agentic.config.example.json",
        [
            {"name": "unit tests", "command": "pytest -q tests"},
            {"name": "more tests", "command": ["pytest", "-q", "more"]},
            {"name": "lint", "command": ["ruff", "check"]},
            {"name": "optional tests", "command": ["pytest", "x"], "required": False},
        ],
    )

    verifiers, kinds, source_text = work._verifiers(root, 2)

    assert verifiers == [
        {"kind": "unit", "command": ["pytest", "-q", "tests"], "acceptance": [0, 1]},
        {"kind": "unit", "command": ["pytest", "-q", "more"], "acceptance": [0, 1]},
        {"kind": "static_analysis", "command": ["ruff", "check"], "acceptance": []},
    ]
    assert kinds == ["unit", "static_analysis"]
    assert source_text == "the 3 required gates in agentic.config.example.json"


def test_the_project_s_own_configuration_wins_over_the_example(plane: Any) -> None:
    root = Path(plane.root)
    shutil.copyfile(root / "agentic.config.json", root / "agentic.config.example.json")
    _write_gates(root / "agentic.config.example.json", [{"name": "ruff", "command": ["ruff"]}])

    assert work._verifiers(root, 1)[2] == "the 1 required gates in agentic.config.json"


def test_gates_that_prove_nothing_name_what_they_are(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    source = Path(__file__).resolve().parents[2] / "agentic.config.example.json"
    shutil.copyfile(source, root / "agentic.config.json")
    _write_gates(
        root / "agentic.config.json",
        [
            {"name": "ruff", "command": ["ruff"]},
            {"name": "coverage", "command": ["coverage"]},
            {"name": "lint", "command": ["lint"]},
        ],
    )

    assert work._verifiers(root, 1) == (
        [],
        [],
        "none of the required gates in agentic.config.json proves behaviour:"
        " coverage, static_analysis",
    )


def test_no_configuration_at_all_is_said_plainly(tmp_path: Path) -> None:
    assert work._verifiers(tmp_path, 1) == (
        [],
        [],
        "no quality configuration to take verifiers from",
    )


# --- protected paths, dependencies and approvals -------------------------------------------


def test_a_protected_directory_covers_what_is_inside_it_and_nothing_beside_it(
    plane: Any,
) -> None:
    assert work._protected(
        plane, ["specs/a.md", "specsheet.md", "AGENTS.md", "AGENTS.md.bak", "src/app.py"]
    ) == ["AGENTS.md", "specs/a.md"]
    assert work._protected(plane, [".github/workflows/ci.yml", ".github/other.yml"]) == [
        ".github/workflows/ci.yml"
    ]


def test_new_work_depends_on_open_work_over_its_scope_and_not_on_finished_work(
    plane: Any,
) -> None:
    (Path(plane.root) / "src" / "third.py").write_text("THIRD = 3\n", encoding="utf-8")
    plane.reconcile()
    first = work.start(plane, "Add a total to src/app.py", claim=False)["task"]["id"]
    second = work.start(plane, "Rename OTHER in src/other.py", claim=False)["task"]["id"]
    third = work.start(plane, "Rename THIRD in src/third.py", claim=False)["task"]["id"]
    everything = ["src/app.py", "src/other.py", "src/third.py"]

    assert work._dependencies(plane, everything) == sorted([first, second, third])
    _set(plane, first, "task", state="COMPLETED")
    _set(plane, third, "task", state="CANCELLED")
    assert work._dependencies(plane, everything) == [second]
    assert work._dependencies(plane, ["docs/readme.md"]) == []


def test_each_gate_command_is_approved_once(plane: Any) -> None:
    fresh = [sys.executable, "-c", "print(1)"]
    other = [sys.executable, "-c", "print(2)"]

    assert work._approve_gates(plane, [{"command": fresh}, {"command": list(fresh)}]) == [fresh]
    assert work._approve_gates(plane, [{"command": fresh}, {"command": other}]) == [other]
    allowed = [list(command) for command in plane.policy()["allowed_commands"]]
    assert fresh in allowed
    assert other in allowed


def test_open_work_whose_scope_contains_the_request_is_linked_by_name(plane: Any) -> None:
    first = work.start(plane, "Share a helper between src/app.py and src/other.py", claim=False)

    again = work.start(plane, "Tidy src/other.py", claim=False)

    assert again["task"]["id"] == first["task"]["id"]
    assert again["matched_by"] == (
        "an open task already covers this scope: Share a helper between src/app.py and src/other.py"
    )


# --- while the work runs -------------------------------------------------------------------


def test_the_latest_checkpoint_is_the_one_with_the_latest_clock(plane: Any) -> None:
    started = work.start(plane, "Add a total to src/app.py")
    task, session = started["task"]["id"], str(started["session"])

    assert work._last_checkpoint(plane, task) is None
    first = work.checkpoint(plane, task, session, reason="slice_complete")["checkpoint"]
    second = work.checkpoint(plane, task, session, reason="handoff")["checkpoint"]

    latest = work._last_checkpoint(plane, task)
    assert latest is not None
    assert latest["id"] == second != first


def test_the_next_ready_task_is_one_the_plane_would_let_start(plane: Any) -> None:
    assert work.next_ready(plane) is None
    first = work.start(plane, "Add a total to src/app.py", claim=False)["task"]["id"]
    blocked = work.start(plane, "Add a helper to src/app.py and src/other.py", claim=False)

    assert blocked["task"]["state"] == "PLANNED"
    ready = work.next_ready(plane)
    assert ready is not None
    assert ready["id"] == first
