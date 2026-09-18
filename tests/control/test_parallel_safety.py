"""Parallel safety classification, pair by pair.

`parallel_safety` decides whether two tasks may run at once, need serialization, or
need review. The existing test walked one contract through each status, so a scope
prefix rule, the boundary intersection or the precedence between reasons could
change unnoticed. Each case compares the whole classification.
"""

from __future__ import annotations

from typing import Any

import pytest

from agentic_discipline.control.workspaces import parallel_safety


def _task(
    scope: list[str], boundaries: list[str] | None = None, risk: str = "LOW"
) -> dict[str, Any]:
    return {"scope": scope, "boundaries": boundaries or [], "risk": risk}


@pytest.mark.parametrize(
    ("left", "right", "overlap"),
    [
        (["."], ["src/app.py"], [(".", "src/app.py")]),
        (["docs"], ["."], [("docs", ".")]),
        (["src/app.py"], ["src/app.py"], [("src/app.py", "src/app.py")]),
        (["src/pkg/mod.py"], ["src"], [("src/pkg/mod.py", "src")]),
        (["src/"], ["src/pkg/mod.py"], [("src/", "src/pkg/mod.py")]),
        (["src"], ["src/"], [("src", "src/")]),
        (
            ["a.py", "src"],
            ["b.py", "src/x.py", "src/y.py"],
            [("src", "src/x.py"), ("src", "src/y.py")],
        ),
    ],
)
def test_overlapping_scopes_conflict_and_list_every_pair(
    left: list[str], right: list[str], overlap: list[tuple[str, str]]
) -> None:
    assert parallel_safety(_task(left, ["api"], "HIGH"), _task(right, ["api"])) == {
        "status": "CONFLICTING",
        "path_overlap": overlap,
        "shared_boundaries": ["api"],
    }


@pytest.mark.parametrize(
    ("left", "right"),
    [(["src"], ["src2/app.py"]), (["src2"], ["src/app.py"]), (["lib/a.py"], ["lib/ab.py"])],
)
def test_similar_names_are_not_overlaps(left: list[str], right: list[str]) -> None:
    assert parallel_safety(_task(left), _task(right))["path_overlap"] == []


def test_shared_boundaries_serialize_disjoint_work() -> None:
    assert parallel_safety(
        _task(["a.py"], ["payments", "api", "auth"], "CRITICAL"),
        _task(["b.py"], ["auth", "reports", "api"]),
    ) == {"status": "SERIALIZE", "path_overlap": [], "shared_boundaries": ["api", "auth"]}


@pytest.mark.parametrize(
    ("left_risk", "right_risk", "status"),
    [
        ("HIGH", "LOW", "PARALLEL_WITH_REVIEW"),
        ("LOW", "CRITICAL", "PARALLEL_WITH_REVIEW"),
        ("CRITICAL", "HIGH", "PARALLEL_WITH_REVIEW"),
        ("CRITICAL", "LOW", "PARALLEL_WITH_REVIEW"),
        ("LOW", "HIGH", "PARALLEL_WITH_REVIEW"),
        ("MEDIUM", "LOW", "SAFE_PARALLEL"),
        ("LOW", "LOW", "SAFE_PARALLEL"),
    ],
)
def test_risk_decides_between_review_and_safe_parallel_work(
    left_risk: str, right_risk: str, status: str
) -> None:
    assert parallel_safety(
        _task(["a.py"], ["left"], left_risk), _task(["b.py"], ["right"], right_risk)
    ) == {
        "status": status,
        "path_overlap": [],
        "shared_boundaries": [],
    }


@pytest.mark.parametrize(("left", "right"), [(["LibX"], ["LibX/a.py"]), (["LibX/a.py"], ["LibX"])])
def test_directory_prefixes_keep_every_character_of_the_name(
    left: list[str], right: list[str]
) -> None:
    assert parallel_safety(_task(left), _task(right))["path_overlap"] == [(left[0], right[0])]
