from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .bootstrap import initialize_project


def migrate_to_v3(project_root: Path, force: bool = False) -> dict[str, Any]:
    root = project_root.resolve()
    had_legacy_config = (root / "agentic.config.json").is_file()
    had_evidence = (root / "artifacts" / "evidence-ledger.jsonl").is_file()
    result = initialize_project(root, force=force)
    report = {
        "from": "2.1" if had_legacy_config else "unknown",
        "to": "3.0",
        "kept": [item for item in ("AGENTS.md", "MASTER_PROMPT.md", "agentic.config.json") if (root / item).exists()],
        "moved": [],
        "generated": [".agentic/constitution", ".agentic/skills", ".agentic/verification", ".agentic/config.json"],
        "conflicts": [],
        "manual_actions": [] if had_evidence else ["review whether an evidence ledger is required"],
        "legacy_evidence_preserved": had_evidence,
        "bootstrap": result,
    }
    output = root / "artifacts" / "migration-v3-report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
