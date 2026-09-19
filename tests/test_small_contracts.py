"""Small promises that nothing larger checks.

A malformed discipline names its file, a verifier command string splits the way the
platform's shell would, a graph whose nodes are not a list reports only that, a
discipline is `always` only when it says so, and the control store waits five
seconds for a busy database instead of failing at once.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline.common import AgenticError
from agentic_discipline.requirements import validate_requirement_graph
from agentic_discipline.skills import load_discipline
from agentic_discipline.verifier import executor


def test_a_malformed_discipline_is_reported_with_its_path(tmp_path: Path) -> None:
    path = tmp_path / "SKILL.md"
    path.write_text("---\nname agentic-x\n---\nbody\n", encoding="utf-8")

    with pytest.raises(AgenticError) as caught:
        load_discipline(path)
    assert str(caught.value) == f"invalid frontmatter line in {path}: 'name agentic-x'"


HEADER = "id: x\nname: agentic-x\ndescription: X\nwhen_to_use: now\n"


@pytest.mark.parametrize(("value", "always"), [("true", True), ("True", True), ("no", False)])
def test_a_discipline_is_always_on_only_when_it_says_true(
    tmp_path: Path, value: str, always: bool
) -> None:
    path = tmp_path / "SKILL.md"
    path.write_text(
        f"---\n{HEADER}always: {value}\n---\nbody\n",
        encoding="utf-8",
    )
    assert load_discipline(path).always is always


def test_a_discipline_without_the_key_is_not_always_on(tmp_path: Path) -> None:
    path = tmp_path / "SKILL.md"
    path.write_text(f"---\n{HEADER}---\nbody\n", encoding="utf-8")
    assert load_discipline(path).always is False


@pytest.mark.parametrize(
    ("platform", "parts"),
    [
        ("posix", ["run", "a b", "c\\d"]),
        ("nt", ["run", '"a b"', "c\\\\d"]),
    ],
)
def test_a_command_string_splits_as_the_platform_shell_would(
    monkeypatch: pytest.MonkeyPatch, platform: str, parts: list[str]
) -> None:
    monkeypatch.setattr(executor.os, "name", platform)
    assert executor._command_parts('run "a b" c\\\\d') == parts


def test_a_graph_whose_nodes_are_not_a_list_reports_only_that() -> None:
    graph = {
        "feature_id": "f",
        "nodes": "A",
        "edges": [{"from": "A", "to": "B", "relation": "verified_by"}],
    }

    assert validate_requirement_graph(graph) == ["nodes: 'A' is not of type 'array'"]


def test_the_store_waits_five_seconds_for_a_busy_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agentic_discipline.control import store as store_module

    seen: dict[str, Any] = {}
    connect = sqlite3.connect

    def spy(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        seen.update(kwargs)
        return connect(*args, **kwargs)

    monkeypatch.setattr(store_module.sqlite3, "connect", spy)
    with store_module.Store(tmp_path / "state.db", create=True):
        pass
    assert seen["timeout"] == 5
