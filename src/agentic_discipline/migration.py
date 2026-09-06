from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .bootstrap import initialize_project

# Paths an earlier installation placed in the repository root. The payload now
# lives under `.agentic/`, so these are legacy copies once migration succeeds.
LEGACY_PATHS = (
    "MASTER_PROMPT.md",
    "skills",
    "policies",
    "schemas",
    "templates",
    "config/risk-weights.json",
)


def _legacy_present(root: Path) -> list[str]:
    return [path for path in LEGACY_PATHS if (root / path).exists()]


def _prune_legacy(root: Path, paths: list[str]) -> list[str]:
    removed: list[str] = []
    for relative in paths:
        target = root / relative
        if target.is_dir():
            shutil.rmtree(target)
        elif target.is_file():
            target.unlink()
        else:
            continue
        removed.append(relative)
        parent = target.parent
        # `config/` only existed to hold the kit's risk weights; leave the
        # directory behind whenever the project put anything else there.
        if parent != root and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
    return removed


def migrate_payload(project_root: Path, force: bool = False, prune: bool = False) -> dict[str, Any]:
    root = project_root.resolve()
    had_existing_config = (root / "agentic.config.json").is_file()
    had_evidence = (root / "artifacts" / "evidence-ledger.jsonl").is_file()
    legacy_before = _legacy_present(root)

    result = initialize_project(root, force=force)

    removed = _prune_legacy(root, legacy_before) if prune else []
    remaining = _legacy_present(root)
    manual_actions: list[str] = []
    if not had_evidence:
        manual_actions.append("review whether an evidence ledger is required")
    if remaining:
        manual_actions.append(
            "remove the legacy root payload with `agentic-discipline migrate --prune`: "
            + ", ".join(remaining)
        )

    report = {
        "from": "earlier-internal" if had_existing_config else "unknown",
        "to": "3.0",
        "kept": [item for item in ("AGENTS.md", "agentic.config.json") if (root / item).exists()],
        "moved": [f"{item} -> .agentic/" for item in legacy_before],
        "removed": removed,
        "legacy_remaining": remaining,
        "generated": [
            ".agentic/constitution",
            ".agentic/skills",
            ".agentic/playbooks",
            ".agentic/verification",
            ".agentic/config.json",
        ],
        "conflicts": [],
        "manual_actions": manual_actions,
        "existing_evidence_preserved": had_evidence,
        "bootstrap": result,
    }
    output = root / "artifacts" / "payload-migration-report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
