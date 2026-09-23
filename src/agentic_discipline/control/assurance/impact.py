"""What the change actually touched, and what else that reaches.

Path and symbol observation comes from the existing bounded discovery, so this never
claims call-level understanding the knowledge graph does not hold.
"""

from __future__ import annotations

from typing import Any

from ..discovery import fingerprint, link_fingerprint


def in_scope(path: str, scope: list[str]) -> bool:
    return any(s == "." or path == s or path.startswith(s.rstrip("/") + "/") for s in scope)


def changed_paths(plane: Any, task: dict[str, Any]) -> list[str]:
    """The task's real diff, measured the same way the change budget measures it."""
    workspace = plane.workspace_root(task)
    current = {**fingerprint(workspace), **link_fingerprint(workspace)}
    initial = {**task.get("initial_files", current), **task.get("initial_links", {})}
    return sorted(p for p in set(initial) | set(current) if initial.get(p) != current.get(p))


def code_entities(plane: Any, paths: list[str]) -> list[dict[str, Any]]:
    wanted = set(paths)
    return [
        e
        for e in plane.store.list("entity")
        if e.get("type") == "file" and e["source_ref"] in wanted
    ]


def symbols_at(plane: Any, paths: list[str]) -> list[str]:
    """Qualified declarations inside the changed files, where discovery resolved them."""
    wanted = set(paths)
    return sorted(
        {
            f"{e['source_ref']}::{e['name']}"
            for e in plane.store.list("entity")
            if e.get("type") == "symbol" and e["source_ref"] in wanted and not e.get("stale")
        }
    )


def reached(plane: Any, paths: list[str], depth: int = 3) -> dict[str, Any]:
    """Requirements and files that depend on what changed, through recorded links only."""
    starts = code_entities(plane, paths)
    dependents: dict[str, dict[str, Any]] = {}
    for entity in starts:
        for other in plane.knowledge.impact(entity["id"], "in", depth):
            if other["lifecycle"] == "ACTIVE" and not other.get("stale"):
                dependents[other["id"]] = other
    requirements = sorted(
        {i for i, e in dependents.items() if e["graph"] == "requirement"},
    )
    files = sorted(
        {e["source_ref"] for e in dependents.values() if e.get("type") == "file"} - set(paths)
    )
    return {
        "changed_paths": list(paths),
        "observed_symbols": symbols_at(plane, paths),
        "dependent_requirements": requirements,
        "dependent_paths": files,
        "resolution": "recorded links between measured files, symbols and requirements",
        "unresolved": "cross-language call graphs and runtime reachability remain UNKNOWN",
    }
