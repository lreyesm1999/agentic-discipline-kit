"""What project detection reports, not merely which profile it picked.

`init` builds the quality configuration from these detections, so the confidence
that ranks them, the evidence that justifies them and the depth limit that bounds
the walk all decide what a new project gets. Existing tests compare the profile
and its directory only, leaving the rest free to change: the weakest manifest
could rank a project, evidence could list a file twice, and the depth limit could
be off by one. Each case compares the whole detection.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentic_discipline.bootstrap import find_contract_root
from agentic_discipline.common import AgenticError
from agentic_discipline.profiles import Profile, detect_projects, load_profile, load_profiles


def _profiles() -> dict[str, Profile]:
    return load_profiles(find_contract_root())


def _detect(root: Path, **options: int) -> list[tuple[str, Path, float, tuple[str, ...]]]:
    return [
        (item.profile, item.root, item.confidence, item.evidence)
        for item in detect_projects(root, _profiles(), **options)
    ]


def test_the_strongest_manifest_sets_the_confidence_and_every_one_is_evidence(
    tmp_path: Path,
) -> None:
    # pyproject.toml is worth 1.0, setup.py 0.9 and requirements*.txt 0.8.
    (tmp_path / "setup.py").write_text("", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("", encoding="utf-8")
    (tmp_path / "requirements-dev.txt").write_text("", encoding="utf-8")

    assert _detect(tmp_path) == [
        ("python", tmp_path, 0.9, ("requirements-dev.txt", "requirements.txt", "setup.py"))
    ]

    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")

    assert _detect(tmp_path) == [
        (
            "python",
            tmp_path,
            1.0,
            ("pyproject.toml", "requirements-dev.txt", "requirements.txt", "setup.py"),
        )
    ]


def test_two_ecosystems_in_one_directory_are_both_reported(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")

    detected = {item[0]: item for item in _detect(tmp_path)}

    assert set(detected) == {"python", "typescript"}
    assert detected["python"][3] == ("pyproject.toml",)
    assert detected["typescript"][3] == ("package.json",)


@pytest.mark.parametrize(("depth", "found"), [(0, False), (1, True), (2, True)])
def test_the_depth_limit_bounds_how_far_the_walk_descends(
    tmp_path: Path, depth: int, found: bool
) -> None:
    nested = tmp_path / "service"
    nested.mkdir()
    (nested / "pyproject.toml").write_text("", encoding="utf-8")

    detections = _detect(tmp_path, max_depth=depth)

    assert bool(detections) is found
    if found:
        assert detections == [("python", nested, 1.0, ("pyproject.toml",))]


def test_a_manifest_in_an_ignored_directory_is_not_a_project(tmp_path: Path) -> None:
    vendored = tmp_path / "node_modules" / "package"
    vendored.mkdir(parents=True)
    (vendored / "pyproject.toml").write_text("", encoding="utf-8")

    assert _detect(tmp_path) == []


def test_a_directory_named_like_a_manifest_is_not_one(tmp_path: Path) -> None:
    # Only a file declares a project; a directory with the same name does not.
    (tmp_path / "pyproject.toml").mkdir()

    assert _detect(tmp_path) == []


def test_the_shallowest_project_of_an_ecosystem_represents_the_nested_ones(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    nested = tmp_path / "packages" / "inner"
    nested.mkdir(parents=True)
    (nested / "pyproject.toml").write_text("", encoding="utf-8")

    assert _detect(tmp_path) == [("python", tmp_path, 1.0, ("pyproject.toml",))]


def test_sibling_projects_of_one_ecosystem_are_both_detected(tmp_path: Path) -> None:
    for name in ("api", "web"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "pyproject.toml").write_text("", encoding="utf-8")

    assert [(p, r) for p, r, _, _ in _detect(tmp_path)] == [
        ("python", tmp_path / "api"),
        ("python", tmp_path / "web"),
    ]


def test_a_nested_duplicate_does_not_hide_later_projects(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "pyproject.toml").write_text("", encoding="utf-8")
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "package.json").write_text("{}", encoding="utf-8")

    assert [(p, r) for p, r, _, _ in _detect(tmp_path)] == [
        ("python", tmp_path),
        ("typescript", tmp_path / "b"),
    ]


def test_a_negative_depth_is_refused_with_its_reason(tmp_path: Path) -> None:
    with pytest.raises(AgenticError) as caught:
        detect_projects(tmp_path, _profiles(), max_depth=-1)
    assert str(caught.value) == "max detection depth must be zero or greater"


def _profile_file(tmp_path: Path, **detector: object) -> Path:
    # Detectors are validated before the quality configuration is looked up.
    path = tmp_path / "profile.json"
    path.write_text(
        json.dumps({"id": "x", "label": "X", "config": "quality.json", "detectors": [detector]}),
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize(
    ("detector", "message"),
    [
        ({"pattern": "", "confidence": 1}, "profile detector 0 pattern is required"),
        ({"pattern": 5, "confidence": 1}, "profile detector 0 pattern is required"),
        (
            {"pattern": "*.x", "confidence": 0},
            "profile detector 0 confidence must be between 0 and 1",
        ),
    ],
    ids=["empty-pattern", "non-text-pattern", "zero-confidence"],
)
def test_invalid_detectors_are_refused(
    tmp_path: Path, detector: dict[str, object], message: str
) -> None:
    path = _profile_file(tmp_path, **detector)
    with pytest.raises(AgenticError) as caught:
        load_profile(path)
    assert str(caught.value) == f"{message}: {path}"


def test_an_unreadable_profile_is_named_in_the_error(tmp_path: Path) -> None:
    path = tmp_path / "profile.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(AgenticError) as caught:
        load_profile(path)
    assert str(caught.value).startswith(f"invalid profile at {path}: ")
