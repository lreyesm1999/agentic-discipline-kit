"""The quality configuration `init` generates from what it detected.

Every gate a new project runs comes from here, so the name that identifies a gate,
the directory it runs in and the refusal to generate two gates with one name are
what keep a multi-project repository honest. Existing tests hand-build a config
and check the parts that consume it, so this step was never compared. Each case
builds a configuration from real profiles and compares it whole.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentic_discipline.bootstrap import find_contract_root
from agentic_discipline.common import AgenticError
from agentic_discipline.profiles import (
    Detection,
    Profile,
    build_quality_config,
    load_profiles,
    requested_projects,
)


def _profiles() -> dict[str, Profile]:
    return load_profiles(find_contract_root())


def _gate_names(profile: Profile) -> list[str]:
    source = json.loads(profile.config_path.read_text(encoding="utf-8"))
    return [gate["name"] for gate in source["gates"]]


def _detection(profile: Profile, root: Path) -> Detection:
    return Detection(
        profile=profile.id, label=profile.label, root=root, confidence=1.0, evidence=("manifest",)
    )


def test_a_root_project_qualifies_its_gates_with_the_profile_alone(tmp_path: Path) -> None:
    profiles = _profiles()
    python = profiles["python"]

    config = build_quality_config(tmp_path, [_detection(python, tmp_path)], profiles)

    assert config["project"] == tmp_path.resolve().name
    assert config["artifacts_dir"] == "artifacts"
    assert [gate["name"] for gate in config["gates"]] == [
        f"python/{name}" for name in _gate_names(python)
    ]
    # A gate at the repository root needs no working directory.
    assert all("working_directory" not in gate for gate in config["gates"])


def test_a_nested_project_carries_its_location_in_the_name_and_the_directory(
    tmp_path: Path,
) -> None:
    profiles = _profiles()
    typescript = profiles["typescript"]
    nested = tmp_path / "web"
    nested.mkdir()

    config = build_quality_config(tmp_path, [_detection(typescript, nested)], profiles)

    assert [gate["name"] for gate in config["gates"]] == [
        f"typescript@web/{name}" for name in _gate_names(typescript)
    ]
    assert all(gate["working_directory"] == "web" for gate in config["gates"])


def test_two_ecosystems_generate_two_named_sets_of_gates(tmp_path: Path) -> None:
    profiles = _profiles()
    nested = tmp_path / "web"
    nested.mkdir()

    config = build_quality_config(
        tmp_path,
        [_detection(profiles["python"], tmp_path), _detection(profiles["typescript"], nested)],
        profiles,
    )

    names = [gate["name"] for gate in config["gates"]]
    assert names == [f"python/{name}" for name in _gate_names(profiles["python"])] + [
        f"typescript@web/{name}" for name in _gate_names(profiles["typescript"])
    ]
    assert len(set(names)) == len(names)


def test_one_project_detected_twice_is_refused_rather_than_duplicated(tmp_path: Path) -> None:
    profiles = _profiles()
    python = profiles["python"]

    with pytest.raises(AgenticError) as caught:
        build_quality_config(
            tmp_path, [_detection(python, tmp_path), _detection(python, tmp_path)], profiles
        )

    assert "duplicate gate name" in str(caught.value)
    assert f"python/{_gate_names(python)[0]}" in str(caught.value)


def test_an_explicitly_requested_profile_is_reported_as_declared(tmp_path: Path) -> None:
    profiles = _profiles()

    (detection,) = requested_projects(tmp_path, ["python"], profiles)

    assert (detection.profile, detection.label) == ("python", profiles["python"].label)
    assert (detection.root, detection.confidence) == (tmp_path.resolve(), 1.0)
    assert detection.evidence == ("explicit profile",)


def test_requesting_an_unknown_profile_names_the_ones_that_exist(tmp_path: Path) -> None:
    profiles = _profiles()

    with pytest.raises(AgenticError) as caught:
        requested_projects(tmp_path, ["python", "cobol"], profiles)

    message = str(caught.value)
    assert "profile not found: cobol" in message
    for available in sorted(profiles):
        assert available in message
