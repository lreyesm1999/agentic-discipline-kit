from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentic_discipline.bootstrap import find_contract_root
from agentic_discipline.common import AgenticError
from agentic_discipline.profiles import detect_projects, load_profile, load_profiles


def test_detection_ignores_dependency_directories_and_collapses_nested_projects(
    tmp_path: Path,
) -> None:
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    nested = tmp_path / "packages" / "web"
    nested.mkdir(parents=True)
    (nested / "package.json").write_text("{}", encoding="utf-8")
    dependency = tmp_path / "node_modules" / "library"
    dependency.mkdir(parents=True)
    (dependency / "pyproject.toml").write_text("", encoding="utf-8")

    detections = detect_projects(tmp_path, load_profiles(find_contract_root()))

    assert [(item.profile, item.root) for item in detections] == [("typescript", tmp_path)]


def test_custom_profile_is_data_driven(tmp_path: Path) -> None:
    quality = tmp_path / "quality.json"
    quality.write_text(
        json.dumps(
            {
                "project": "rust",
                "gates": [{"name": "test", "command": ["cargo", "test"]}],
            }
        ),
        encoding="utf-8",
    )
    descriptor = tmp_path / "rust.json"
    descriptor.write_text(
        json.dumps(
            {
                "id": "rust",
                "label": "Rust",
                "config": "quality.json",
                "detectors": [{"pattern": "Cargo.toml", "confidence": 1}],
            }
        ),
        encoding="utf-8",
    )

    profile = load_profile(descriptor)

    assert profile.id == "rust"
    assert profile.config_path == quality.resolve()


def test_profile_rejects_invalid_confidence(tmp_path: Path) -> None:
    descriptor = tmp_path / "invalid.json"
    descriptor.write_text(
        json.dumps(
            {
                "id": "bad",
                "label": "Bad",
                "config": "missing.json",
                "detectors": [{"pattern": "x", "confidence": 2}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(AgenticError, match="confidence"):
        load_profile(descriptor)


def test_detection_rejects_negative_depth(tmp_path: Path) -> None:
    with pytest.raises(AgenticError, match="depth"):
        detect_projects(tmp_path, load_profiles(find_contract_root()), max_depth=-1)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("id", "", "profile id"),
        ("label", "", "profile label"),
        ("config", "", "profile config"),
        ("detectors", {}, "detectors"),
        ("detectors", ["bad"], "detector 0"),
        ("config", "missing.json", "quality configuration"),
    ],
)
def test_profile_rejects_invalid_descriptor_fields(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    descriptor = tmp_path / f"invalid-{field}.json"
    data: dict[str, object] = {
        "id": "custom",
        "label": "Custom",
        "config": "quality.json",
        "detectors": [],
    }
    data[field] = value
    descriptor.write_text(json.dumps(data), encoding="utf-8")
    (tmp_path / "quality.json").write_text(
        json.dumps({"project": "custom", "gates": [{"name": "test", "command": ["true"]}]}),
        encoding="utf-8",
    )
    with pytest.raises(AgenticError, match=message):
        load_profile(descriptor)
