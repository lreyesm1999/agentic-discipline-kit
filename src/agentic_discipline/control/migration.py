"""Explicit legacy import and reversible knowledge changes; preserve original artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..requirements import validate_requirement_graph
from .contracts import digest, entity_contract, require, uid
from .plane import Plane


def import_legacy(plane: Plane, path: Path, dry_run: bool = False) -> dict[str, Any]:
    graph = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_requirement_graph(graph)
    require(not errors, "INVALID_LEGACY_GRAPH", "; ".join(errors))
    source = str(path.resolve())
    source_hash = digest(graph)
    prior = [r for r in plane.store.list("import") if r["source_hash"] == source_hash]
    if prior:
        return {"already_imported": True, "mapping": prior[0]["mapping"]}
    if dry_run:
        return {
            "dry_run": True,
            "nodes": len(graph["nodes"]),
            "edges": len(graph["edges"]),
            "source": source,
            "writes": ["knowledge database"],
            "original_unchanged": True,
        }
    mapping = {}
    with plane.store.transaction():
        plane.store.bump()
        for node in graph["nodes"]:
            kind = node["type"]
            payload = {
                "id": uid("ENT"),
                "graph": "code"
                if kind == "code"
                else "evidence"
                if kind in {"test", "evidence"}
                else "execution"
                if kind == "task"
                else "requirement",
                "type": kind,
                "name": node["id"],
                "source_ref": source,
                "authority": "historical",
                "observation": "DECLARED",
                "confidence": 0.5,
                "lifecycle": "HISTORICAL",
                "stale": False,
                "legacy_id": node["id"],
                "legacy_payload": node,
            }
            entity_contract(payload)
            created = plane.store.put("entity", payload)
            mapping[node["id"]] = created["id"]
        for edge in graph["edges"]:
            plane.store.db.execute(
                "INSERT INTO edges VALUES (?,?,?,?)",
                (uid("EDGE"), mapping[edge["from"]], mapping[edge["to"]], edge["relation"]),
            )
        plane.store.put(
            "import",
            {
                "source": source,
                "source_hash": source_hash,
                "mapping": mapping,
                "disposition": "HISTORICAL_REVIEW_REQUIRED",
            },
        )
    return {
        "mapping": mapping,
        "disposition": "HISTORICAL_REVIEW_REQUIRED",
        "original_unchanged": True,
    }


def rollback_changeset(plane: Plane, identifier: str, reason: str) -> dict[str, Any]:
    require(bool(reason.strip()), "REASON_REQUIRED", "Rollback requires a reason")
    with plane.store.transaction():
        change = plane.store.get(identifier, "changeset")
        require(change["status"] == "APPLIED", "INVALID_CHANGESET", "Changeset is not applied")
        # Refuse to overwrite later work; the rollback itself gets a new revision.
        snapshots = []
        for entity_id in change["entities"]:
            history = plane.store.history(entity_id)
            applied = [h for h in history if h["knowledge_version"] == change["base_version"] + 1]
            current = plane.store.get(entity_id, "entity")
            require(
                applied and current["version"] == applied[-1]["version"],
                "VERSION_CONFLICT",
                "Entity changed after this changeset",
            )
            snapshots.append((current, history[-2]["payload"] if len(history) > 1 else None))
        plane.store.bump()
        for current, previous in snapshots:
            payload = previous or {**current, "lifecycle": "HISTORICAL", "lifecycle_reason": reason}
            require(
                not (current["lifecycle"] != "ACTIVE" and payload["lifecycle"] == "ACTIVE"),
                "RESURRECTION_BLOCKED",
                "Restoring active intent requires explicit replacement review",
            )
            plane.store.put("entity", {**payload, "id": current["id"]}, expected=current["version"])
        for edge in plane.store.db.execute(
            "SELECT source,target FROM edges WHERE relation='depends_on'"
        ):
            left, right = plane.store.get(edge[0], "entity"), plane.store.get(edge[1], "entity")
            require(
                left["lifecycle"] != "ACTIVE" or right["lifecycle"] == "ACTIVE",
                "RETIRED_DEPENDENCY",
                "Rollback would retire knowledge with active dependents",
            )
        return plane.store.put(
            "changeset",
            {**change, "status": "ROLLED_BACK", "rollback_reason": reason},
            expected=change["version"],
        )
