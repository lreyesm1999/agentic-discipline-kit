"""Payload migration report, field by field.

`migrate` moves an earlier root-level installation under `.agentic/` and writes a
report the user reads to finish by hand. Existing tests checked the target version
and that pruning removed the legacy paths, so the report could misstate where the
project came from, drop a manual action or lose the evidence flag unnoticed.
"""

from __future__ import annotations

import json
from pathlib import Path

from agentic_discipline.bootstrap import initialize_project
from agentic_discipline.migration import LEGACY_PATHS, migrate_payload

GENERATED = [
    ".agentic/constitution",
    ".agentic/skills",
    ".agentic/playbooks",
    ".agentic/verification",
    ".agentic/config.json",
]
LEDGER_ACTION = "review whether an evidence ledger is required"


def _legacy(project: Path, paths: tuple[str, ...] = LEGACY_PATHS) -> None:
    for relative in paths:
        target = project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if Path(relative).suffix:
            target.write_text("stale\n", encoding="utf-8")
        else:
            target.mkdir()
            (target / "leftover.md").write_text("stale\n", encoding="utf-8")


def _saved(project: Path) -> str:
    return (project / "artifacts" / "payload-migration-report.json").read_text(encoding="utf-8")


def test_fresh_project_report(tmp_path: Path) -> None:
    project = tmp_path / "fresh"
    project.mkdir()

    report = migrate_payload(project)

    assert (project / "agentic.config.json").is_file()
    kept = ["agentic.config.json"]
    if (project / "AGENTS.md").exists():
        kept.insert(0, "AGENTS.md")
    assert report == {
        "from": "unknown",
        "to": "3.0",
        "kept": kept,
        "moved": [],
        "removed": [],
        "legacy_remaining": [],
        "generated": GENERATED,
        "conflicts": [],
        "manual_actions": [LEDGER_ACTION],
        "existing_evidence_preserved": False,
        "bootstrap": report["bootstrap"],
    }
    assert report["bootstrap"]["actions"]
    assert _saved(project) == json.dumps(report, indent=2) + "\n"


def test_earlier_installation_report_lists_what_is_left_to_do(tmp_path: Path) -> None:
    project = tmp_path / "earlier"
    initialize_project(project)
    (project / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    ledger = project / "artifacts" / "evidence-ledger.jsonl"
    ledger.parent.mkdir(exist_ok=True)
    ledger.write_text('{"id": "E-1"}\n', encoding="utf-8")
    present = ("MASTER_PROMPT.md", "schemas", "config/risk-weights.json")
    _legacy(project, present)

    report = migrate_payload(project)

    assert {k: report[k] for k in report if k not in {"generated", "bootstrap"}} == {
        "from": "earlier-internal",
        "to": "3.0",
        "kept": ["AGENTS.md", "agentic.config.json"],
        "moved": [f"{item} -> .agentic/" for item in present],
        "removed": [],
        "legacy_remaining": list(present),
        "conflicts": [],
        "manual_actions": [
            "remove the legacy root payload with `agentic-discipline migrate --prune`: "
            "MASTER_PROMPT.md, schemas, config/risk-weights.json"
        ],
        "existing_evidence_preserved": True,
    }
    assert ledger.read_text(encoding="utf-8") == '{"id": "E-1"}\n'
    assert _saved(project) == json.dumps(report, indent=2) + "\n"


def test_prune_removes_legacy_paths_in_order_and_their_emptied_directory(tmp_path: Path) -> None:
    project = tmp_path / "legacy"
    project.mkdir()
    _legacy(project)

    report = migrate_payload(project, prune=True)

    assert report["removed"] == list(LEGACY_PATHS)
    assert report["moved"] == [f"{item} -> .agentic/" for item in LEGACY_PATHS]
    assert (report["legacy_remaining"], report["manual_actions"]) == ([], [LEDGER_ACTION])
    assert not (project / "config").exists()
    assert project.is_dir()


def test_force_is_passed_to_the_bootstrap(tmp_path: Path) -> None:
    project = tmp_path / "forced"
    initialize_project(project)
    config = project / "agentic.config.json"
    config.write_text("{}\n", encoding="utf-8")

    migrate_payload(project)
    assert config.read_text(encoding="utf-8") == "{}\n"

    migrate_payload(project, force=True)
    assert json.loads(config.read_text(encoding="utf-8"))["gates"]
