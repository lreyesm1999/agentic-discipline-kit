from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from .validation import validate_schema

RELATION_TYPES: dict[str, tuple[set[str], set[str]]] = {
    "specified_by": ({"requirement"}, {"spec"}),
    "verified_by": ({"requirement", "spec", "acceptance"}, {"acceptance", "test"}),
    "planned_by": ({"requirement", "spec", "acceptance"}, {"task"}),
    "implemented_by": (
        {"requirement", "spec", "acceptance", "task"},
        {"code"},
    ),
    "evidenced_by": (
        {"requirement", "spec", "acceptance", "task", "test", "code"},
        {"evidence"},
    ),
    "depends_on": (
        {"requirement", "spec", "acceptance", "task", "test", "code", "evidence"},
        {"requirement", "spec", "acceptance", "task", "test", "code", "evidence"},
    ),
}


def validate_requirement_graph(
    graph: dict[str, Any], base_path: Path | None = None, complete: bool = False
) -> list[str]:
    errors = validate_schema(graph, "requirement-graph.schema.json")
    raw_nodes = graph.get("nodes", [])
    raw_edges = graph.get("edges", [])
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        return errors

    nodes: dict[str, dict[str, Any]] = {}
    for index, node in enumerate(raw_nodes):
        if not isinstance(node, dict) or not isinstance(node.get("id"), str):
            continue
        node_id = node["id"]
        if node_id in nodes:
            errors.append(f"nodes.{index}.id: duplicate node id {node_id!r}")
            continue
        nodes[node_id] = node
        node_path = node.get("path")
        if base_path is not None and isinstance(node_path, str):
            if not (base_path / node_path).is_file():
                errors.append(f"nodes.{index}.path: file not found: {node_path}")

    adjacency: dict[str, set[str]] = defaultdict(set)
    for index, edge in enumerate(raw_edges):
        if not isinstance(edge, dict):
            continue
        source = edge.get("from")
        target = edge.get("to")
        relation = edge.get("relation")
        if source not in nodes:
            errors.append(f"edges.{index}.from: unknown node {source!r}")
        if target not in nodes:
            errors.append(f"edges.{index}.to: unknown node {target!r}")
        if source == target:
            errors.append(f"edges.{index}: self-reference is not allowed")
        if source not in nodes or target not in nodes or relation not in RELATION_TYPES:
            continue
        allowed_sources, allowed_targets = RELATION_TYPES[relation]
        source_type = nodes[source].get("type")
        target_type = nodes[target].get("type")
        if source_type not in allowed_sources or target_type not in allowed_targets:
            errors.append(
                f"edges.{index}: {relation} cannot connect {source_type} to {target_type}"
            )
            continue
        if relation != "depends_on":
            adjacency[source].add(target)

    if complete:
        evidence_nodes = {
            node_id for node_id, node in nodes.items() if node.get("type") == "evidence"
        }
        for node_id, node in nodes.items():
            if node.get("type") != "requirement":
                continue
            visited = {node_id}
            queue = deque([node_id])
            reaches_evidence = False
            while queue:
                current = queue.popleft()
                if current in evidence_nodes:
                    reaches_evidence = True
                    break
                for target in adjacency.get(current, set()):
                    if target not in visited:
                        visited.add(target)
                        queue.append(target)
            if not reaches_evidence:
                errors.append(f"requirements.{node_id}: no traceability path reaches evidence")
    return errors


def orphan_requirements(graph: dict[str, Any]) -> list[str]:
    nodes = {
        node["id"]: node
        for node in graph.get("nodes", [])
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    }
    outgoing: dict[str, list[dict[str, Any]]] = {}

    for edge in graph.get("edges", []):
        if not isinstance(edge, dict):
            continue
        source = edge.get("from")
        target = edge.get("to")
        relation = edge.get("relation")
        if (
            not isinstance(source, str)
            or not isinstance(target, str)
            or not isinstance(relation, str)
            or source not in nodes
            or target not in nodes
            or relation not in RELATION_TYPES
        ):
            continue
        allowed_sources, allowed_targets = RELATION_TYPES[relation]
        if (
            nodes[source].get("type") in allowed_sources
            and nodes[target].get("type") in allowed_targets
        ):
            outgoing.setdefault(source, []).append(edge)

    requirements = [node for node in nodes.values() if node.get("type") == "requirement"]
    return [node["id"] for node in requirements if not outgoing.get(node["id"])]
