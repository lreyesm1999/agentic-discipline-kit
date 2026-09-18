"""Knowledge impact analysis, traversal by traversal.

`impact` answers "what else is affected if this changes" for agents and reviewers.
Existing tests checked one dependent, so the traversal direction, the depth limit,
repeated or cyclic paths, the result order or the argument checks could change
unnoticed. Each case compares the exact entities returned.
"""

from __future__ import annotations

from typing import Any

import pytest
from test_kernel import entity

from agentic_discipline.control.contracts import ControlError


def _nodes(project: Any, *specs: tuple[str, str]) -> dict[str, dict[str, Any]]:
    created = project.knowledge.apply(
        [entity(name, graph) for name, graph in specs], project.store.knowledge_version, "seed"
    )["entities"]
    return {item["name"]: item for item in created}


def _entities(project: Any, nodes: dict[str, dict[str, Any]], *names: str) -> list[dict[str, Any]]:
    return [project.store.get(i, "entity") for i in sorted(nodes[n]["id"] for n in names)]


@pytest.fixture
def chain(project: Any) -> dict[str, dict[str, Any]]:
    """a depends on b, b on c, c on d; x is unrelated."""
    nodes = _nodes(project, *((name, "requirement") for name in "abcdx"))
    for source, target in (("a", "b"), ("b", "c"), ("c", "d")):
        project.knowledge.link(nodes[source]["id"], nodes[target]["id"], "depends_on")
    return nodes


def test_inward_impact_lists_every_transitive_dependent_sorted_by_id(
    project: Any, chain: dict[str, dict[str, Any]]
) -> None:
    assert project.knowledge.impact(chain["d"]["id"]) == _entities(project, chain, "a", "b", "c")
    assert project.knowledge.impact(chain["d"]["id"], "in") == _entities(
        project, chain, "a", "b", "c"
    )


def test_outward_impact_lists_every_transitive_dependency(
    project: Any, chain: dict[str, dict[str, Any]]
) -> None:
    assert project.knowledge.impact(chain["a"]["id"], "out") == _entities(
        project, chain, "b", "c", "d"
    )
    assert project.knowledge.impact(chain["x"]["id"], "out") == []


@pytest.mark.parametrize(
    ("depth", "names"),
    [(0, []), (1, ["c"]), (2, ["b", "c"]), (3, ["a", "b", "c"]), (20, ["a", "b", "c"])],
)
def test_depth_limits_how_far_impact_travels(
    project: Any, chain: dict[str, dict[str, Any]], depth: int, names: list[str]
) -> None:
    assert project.knowledge.impact(chain["d"]["id"], depth=depth) == _entities(
        project, chain, *names
    )


def test_default_depth_is_four(project: Any) -> None:
    nodes = _nodes(project, *((name, "requirement") for name in "abcdef"))
    for source, target in zip("abcde", "bcdef", strict=True):
        project.knowledge.link(nodes[source]["id"], nodes[target]["id"], "depends_on")
    assert project.knowledge.impact(nodes["f"]["id"]) == _entities(
        project, nodes, "b", "c", "d", "e"
    )


def test_shared_and_cyclic_paths_are_visited_once(project: Any) -> None:
    nodes = _nodes(
        project, ("top", "requirement"), ("left", "requirement"), ("right", "requirement")
    )
    nodes.update(_nodes(project, ("module", "code")))
    link = project.knowledge.link
    link(nodes["top"]["id"], nodes["left"]["id"], "depends_on")
    link(nodes["top"]["id"], nodes["right"]["id"], "depends_on")
    link(nodes["left"]["id"], nodes["module"]["id"], "implemented_by")
    link(nodes["right"]["id"], nodes["module"]["id"], "implemented_by")
    link(nodes["module"]["id"], nodes["top"]["id"], "depends_on")

    assert project.knowledge.impact(nodes["module"]["id"]) == _entities(
        project, nodes, "left", "right", "top"
    )
    assert project.knowledge.impact(nodes["top"]["id"], "out") == _entities(
        project, nodes, "left", "module", "right"
    )


@pytest.mark.parametrize(("direction", "depth"), [("both", 4), ("in", -1), ("out", 21)])
def test_invalid_traversals_are_refused(
    project: Any, chain: dict[str, dict[str, Any]], direction: str, depth: int
) -> None:
    with pytest.raises(ControlError) as caught:
        project.knowledge.impact(chain["a"]["id"], direction, depth)
    assert (caught.value.code, str(caught.value)) == ("INVALID_QUERY", "Invalid traversal")


def test_unknown_or_non_entity_starts_are_not_found_before_arguments_are_checked(
    project: Any,
) -> None:
    for identifier in ("ENT-missing", project.store.list("project")[0]["id"]):
        with pytest.raises(ControlError) as caught:
            project.knowledge.impact(identifier, "both", 99)
        assert (caught.value.code, str(caught.value)) == (
            "NOT_FOUND",
            f"Record not found: {identifier}",
        )
