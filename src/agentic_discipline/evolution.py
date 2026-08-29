from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .common import AgenticError, changed_files, run_git
from .validation import load_json, validate_schema

TEMPORARY_PATTERNS = ("debug_", "inspect_", "reproduce_", "migration_helper")
FALLBACK_PATTERN = re.compile(
    r"except\s+[^:]+:\s*[\r\n]+\s*(?:return|use_|fallback)", re.IGNORECASE
)


def lifecycle_path(project_root: Path) -> Path:
    return project_root.resolve() / ".agentic" / "evolution" / "lifecycle.json"


def load_lifecycle(project_root: Path) -> dict[str, Any]:
    path = lifecycle_path(project_root)
    if not path.exists():
        return {"schema_version": "1", "artifacts": []}
    registry = load_json(path, "evolution registry")
    errors = validate_schema(registry, "evolution.schema.json")
    if errors:
        raise AgenticError("invalid evolution registry: " + "; ".join(errors))
    return registry


def register_lifecycle(project_root: Path, item: dict[str, Any]) -> dict[str, Any]:
    required = {"id", "path", "state"}
    if not required.issubset(item):
        raise AgenticError("lifecycle item requires id, path, and state")
    registry = load_lifecycle(project_root)
    registry["artifacts"] = [
        existing for existing in registry["artifacts"] if existing["id"] != item["id"]
    ]
    registry["artifacts"].append(item)
    output = lifecycle_path(project_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    return item


def hygiene(project_root: Path, base_ref: str | None = None) -> dict[str, Any]:
    root = project_root.resolve()
    added: list[str] = []
    changed: list[str] = []
    if base_ref:
        try:
            changed = changed_files(base_ref, cwd=root)
            diff = run_git(["diff", "--unified=0", base_ref, "--"], cwd=root)
        except AgenticError:
            diff = ""
    else:
        diff = ""
    for relative in changed:
        if relative not in added and any(
            Path(relative).name.lower().startswith(prefix) for prefix in TEMPORARY_PATTERNS
        ):
            added.append(relative)
    fallbacks = [
        line.strip()
        for line in diff.splitlines()
        if line.startswith("+") and FALLBACK_PATTERN.search(line[1:])
    ]
    lifecycle = load_lifecycle(root)
    temporary = [item for item in lifecycle["artifacts"] if item["state"] == "TEMPORARY"]
    deprecated = [
        item
        for item in lifecycle["artifacts"]
        if item["state"] == "DEPRECATE" and not item.get("removal_condition")
    ]
    unresolved = [
        item["id"]
        for item in lifecycle["artifacts"]
        if item["state"] == "REMOVE" and (root / item["path"]).exists()
    ]
    result = {
        "status": "FAIL" if fallbacks or deprecated or unresolved or added else "PASS",
        "temporary_artifacts": temporary,
        "unauthorized_fallbacks": fallbacks,
        "superseded_active": [],
        "stale_feature_flags": [],
        "orphan_tests": [],
        "stale_instructions": [],
        "unresolved_deprecations": deprecated,
        "unresolved_removals": unresolved,
        "new_temporary_artifacts": added,
    }
    return result
