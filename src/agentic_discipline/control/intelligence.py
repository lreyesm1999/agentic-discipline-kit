"""Read the optional Agentic Intelligence handoff for an exact task ID."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

UTF8_ENCODING = "utf-8"
GLOBAL_BLOCKER_CODES = frozenset({"missing_core_type", "missing_research", "discovery_gap"})


def intelligence_snapshot(root: Path, task_id: str) -> dict[str, Any]:
    directory = root / ".agentic" / "intelligence"
    empty: dict[str, Any] = {"reasons": [], "constraints": [], "binding": None}
    if not directory.exists():
        return empty
    if directory.is_symlink() or not directory.is_dir():
        return {**empty, "reasons": [{"type": "intelligence_invalid", "detail": "handoff directory"}]}

    def read_json(name: str) -> Any:
        path = directory / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 2_000_000:
            raise ValueError(f"Invalid handoff artifact: {name}")
        return json.loads(path.read_text(encoding=UTF8_ENCODING))

    try:
        readiness = read_json("readiness.json")
        if (not isinstance(readiness, dict) or not isinstance(readiness.get("ready"), bool)
                or not isinstance(readiness.get("blockers"), list)
                or readiness["ready"] == bool(readiness["blockers"])):
            raise ValueError("Invalid readiness report")
        if any(not isinstance(row, dict) or not isinstance(row.get("code"), str)
               or not isinstance(row.get("id"), str) for row in readiness["blockers"]):
            raise ValueError("Invalid readiness blocker")
        reasons = [
            {"type": "intelligence_blocker", "code": row.get("code"), "id": row.get("id")}
            for row in readiness["blockers"]
            if row["id"] == task_id or row["code"] in GLOBAL_BLOCKER_CODES
        ]
        constraints: list[dict[str, Any]] = []
        context = read_json("latest-context.json")
        if not isinstance(context, dict) or not isinstance(context.get("items"), list):
            raise ValueError("Invalid task context")
        if context.get("root_id") != task_id:
            raise ValueError("Handoff context belongs to a different task")
        included_ids = {item["node"].get("id") for item in context["items"]
                        if isinstance(item, dict) and isinstance(item.get("node"), dict)}
        reasons.extend(
            {"type": "intelligence_blocker", "code": row.get("code"), "id": row.get("id")}
            for row in readiness["blockers"]
            if row["id"] != task_id and any(part in included_ids for part in row["id"].split(","))
        )
        path = directory / "executable-constraints.jsonl"
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 2_000_000:
            raise ValueError("Invalid executable constraints artifact")
        for line in path.read_text(encoding=UTF8_ENCODING).splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                raise ValueError("Invalid executable constraint row")
            if row["id"] in included_ids and row.get("severity") == "mandatory":
                constraints.append(row)
                if row.get("normative") is not True:
                    reasons.append({"type": "intelligence_constraint_unapproved", "id": row["id"]})
        binding_input = {"reasons": reasons, "constraints": constraints}
        binding = hashlib.sha256(json.dumps(binding_input, sort_keys=True).encode()).hexdigest()
        return {"reasons": reasons, "constraints": constraints, "binding": binding}
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return {**empty, "reasons": [{"type": "intelligence_invalid", "detail": str(exc)}]}
