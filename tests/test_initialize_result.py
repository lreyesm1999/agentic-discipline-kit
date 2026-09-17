"""`initialize_project` result, field by field.

The init result feeds the human report, `--json` output and every installer surface.
Existing tests checked a few fields of real runs, so detection options could be
dropped, the generic fallback could change shape, or the relaxed and baseline gate
summaries could pick the wrong gates unnoticed. Adapter emission is recorded rather
than run so each case pins exactly what `initialize_project` decides.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline import adapters, bootstrap
from agentic_discipline.bootstrap import find_contract_root, initialize_project
from agentic_discipline.profiles import load_profiles, requested_projects

GATES = [
    {"name": "lint", "command": ["ruff", "check", "."]},
    {"name": "typecheck", "note": "disabled by init: mypy missing", "required": False},
    {"name": "docs", "note": "optional by design", "required": False},
    {"name": "tests", "note": "reviewed", "required": True},
    {"name": "units", "note": "no required flag"},
    {"name": "syntax", "note": "added by init: nothing else runs"},
    {"name": "second", "note": "added by init: later"},
    "not a gate",
]


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    calls: list[Any] = []

    def sync(root: Path, names: Any, dry_run: bool = False) -> dict[str, Any]:
        calls.append(("sync", root, names, dry_run))
        return {
            "adapters": ["generic"],
            "labels": ["Generic AGENTS.md"],
            "disciplines": ["one", "two"],
            "actions": ["WRITE AGENTS.md", Path("rules.md")],
        }

    def detect(root: Path) -> list[str]:
        calls.append(("detect", root))
        return ["generic", "claude"]

    monkeypatch.setattr(adapters, "sync_adapters", sync)
    monkeypatch.setattr(adapters, "detect_adapters", detect)
    monkeypatch.setattr(
        bootstrap, "annotate_gate_availability", lambda root, config: {**config, "gates": GATES}
    )
    return calls


def test_result_summarizes_detection_adapters_and_gates(
    tmp_path: Path, recorded: list[Any]
) -> None:
    root = tmp_path / "project"

    result = initialize_project(root, profile_ids=["python"])

    kit = find_contract_root().resolve()
    detections = requested_projects(root.resolve(), ["python"], load_profiles(kit))
    actions = result.pop("actions")
    assert result == {
        "status": "PASS",
        "target": str(root.resolve()),
        "dry_run": False,
        "profiles": ["python"],
        "detections": [d.report(root.resolve()) for d in detections],
        "config": str(root.resolve() / "agentic.config.json"),
        "adapters": ["generic"],
        "adapter_labels": ["Generic AGENTS.md"],
        "disciplines": ["one", "two"],
        "gates": len(GATES),
        "relaxed_gates": [
            {"name": "typecheck", "note": "disabled by init: mypy missing"},
            {"name": "docs", "note": "optional by design"},
        ],
        "baseline_gate": "syntax",
    }
    assert actions[-3:] == ["WRITE AGENTS.md", "rules.md", f"READY {root.resolve()}"]
    assert f"WRITE {root.resolve() / 'agentic.config.json'}" in actions
    assert recorded == [
        ("detect", root.resolve()),
        ("sync", root.resolve(), ["generic", "claude"], False),
    ]
    written = json.loads((root / "agentic.config.json").read_text(encoding="utf-8"))
    assert written["gates"] == GATES


def test_undetected_projects_fall_back_to_the_generic_profile(
    tmp_path: Path, recorded: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    depths: list[int] = []

    def nothing(root: Path, profiles: Any, max_depth: int = 4) -> list[Any]:
        depths.append(max_depth)
        return []

    monkeypatch.setattr(bootstrap, "detect_projects", nothing)
    root = tmp_path / "empty"

    result = initialize_project(root, max_depth=2, adapters=["generic"])

    generic = load_profiles(find_contract_root().resolve())["generic"]
    assert depths == [2]
    assert result["profiles"] == ["generic"]
    assert result["detections"] == [
        {
            "profile": generic.id,
            "label": generic.label,
            "root": ".",
            "confidence": 0.0,
            "evidence": ["no known project manifest detected"],
        }
    ]
    assert recorded == [("sync", root.resolve(), ["generic"], False)]

    initialize_project(tmp_path / "default-depth", adapters=["generic"])
    assert depths == [2, 4]


def test_dry_run_writes_nothing_and_says_so(tmp_path: Path, recorded: list[Any]) -> None:
    root = tmp_path / "planned"

    result = initialize_project(root, profile_ids=["python"], adapters=[], dry_run=True)

    assert result["dry_run"] is True
    assert not root.exists()
    assert recorded == [("sync", root.resolve(), [], True)]


def test_existing_configuration_is_kept_unless_forced(tmp_path: Path, recorded: list[Any]) -> None:
    root = tmp_path / "project"
    root.mkdir()
    config = root / "agentic.config.json"
    config.write_text('{"project": "mine"}\n', encoding="utf-8")

    kept = initialize_project(root, profile_ids=["python"], adapters=["generic"])
    assert config.read_text(encoding="utf-8") == '{"project": "mine"}\n'
    assert f"SKIP {config.resolve()} (already exists)" in kept["actions"]

    forced = initialize_project(root, profile_ids=["python"], adapters=["generic"], force=True)
    assert json.loads(config.read_text(encoding="utf-8"))["gates"] == GATES
    assert f"WRITE {config.resolve()}" in forced["actions"]
