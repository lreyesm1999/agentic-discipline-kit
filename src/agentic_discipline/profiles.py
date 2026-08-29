from __future__ import annotations

import copy
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from .common import AgenticError
from .validation import load_quality_config

IGNORED_DIRECTORIES = {
    ".git",
    ".idea",
    ".tox",
    ".venv",
    ".vscode",
    "__pycache__",
    "artifacts",
    "bin",
    "build",
    "dist",
    "node_modules",
    "obj",
    "target",
    "venv",
}


@dataclass(frozen=True)
class Detector:
    pattern: str
    confidence: float


@dataclass(frozen=True)
class Profile:
    id: str
    label: str
    config_path: Path
    detectors: tuple[Detector, ...]


@dataclass(frozen=True)
class Detection:
    profile: str
    label: str
    root: Path
    confidence: float
    evidence: tuple[str, ...]

    def report(self, repository_root: Path) -> dict[str, Any]:
        result = asdict(self)
        relative = self.root.relative_to(repository_root)
        result["root"] = relative.as_posix() if relative.parts else "."
        result["evidence"] = list(self.evidence)
        return result


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AgenticError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise AgenticError(f"invalid {label} at {path}: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise AgenticError(f"{label} must be a JSON object: {path}")
    return value


def load_profile(path: Path) -> Profile:
    data = _load_json(path, "profile")
    profile_id = data.get("id")
    label = data.get("label")
    config = data.get("config")
    detectors_data = data.get("detectors", [])
    if not isinstance(profile_id, str) or not profile_id.strip():
        raise AgenticError(f"profile id is required: {path}")
    if not isinstance(label, str) or not label.strip():
        raise AgenticError(f"profile label is required: {path}")
    if not isinstance(config, str) or not config.strip():
        raise AgenticError(f"profile config is required: {path}")
    if not isinstance(detectors_data, list):
        raise AgenticError(f"profile detectors must be an array: {path}")

    detectors: list[Detector] = []
    for index, item in enumerate(detectors_data):
        if not isinstance(item, dict):
            raise AgenticError(f"profile detector {index} must be an object: {path}")
        pattern = item.get("pattern")
        confidence = item.get("confidence")
        if not isinstance(pattern, str) or not pattern.strip():
            raise AgenticError(f"profile detector {index} pattern is required: {path}")
        if not isinstance(confidence, (int, float)) or not 0 < float(confidence) <= 1:
            raise AgenticError(
                f"profile detector {index} confidence must be between 0 and 1: {path}"
            )
        detectors.append(Detector(pattern=pattern, confidence=float(confidence)))

    config_path = (path.parent / config).resolve()
    if not config_path.is_file():
        raise AgenticError(f"profile quality configuration not found: {config_path}")
    load_quality_config(config_path)
    return Profile(
        id=profile_id.strip(),
        label=label.strip(),
        config_path=config_path,
        detectors=tuple(detectors),
    )


def load_profiles(contract_root: Path, extra_paths: Iterable[Path] = ()) -> dict[str, Profile]:
    descriptor_paths = sorted((contract_root / "config" / "profiles").glob("*.json"))
    descriptor_paths.extend(Path(path) for path in extra_paths)
    profiles: dict[str, Profile] = {}
    for path in descriptor_paths:
        profile = load_profile(path.resolve())
        if profile.id in profiles:
            raise AgenticError(f"duplicate profile id: {profile.id}")
        profiles[profile.id] = profile
    if "generic" not in profiles:
        raise AgenticError("generic profile is not available")
    return profiles


def _candidate_directories(root: Path, max_depth: int) -> list[Path]:
    candidates: list[Path] = []
    for current, directories, _files in os.walk(root):
        current_path = Path(current)
        depth = len(current_path.relative_to(root).parts)
        directories[:] = sorted(
            directory
            for directory in directories
            if directory not in IGNORED_DIRECTORIES and depth < max_depth
        )
        candidates.append(current_path)
    return candidates


def detect_projects(root: Path, profiles: dict[str, Profile], max_depth: int = 4) -> list[Detection]:
    if max_depth < 0:
        raise AgenticError("max detection depth must be zero or greater")
    root = root.resolve()
    detections: list[Detection] = []
    for directory in _candidate_directories(root, max_depth):
        for profile in profiles.values():
            if not profile.detectors:
                continue
            matches: list[tuple[str, float]] = []
            for detector in profile.detectors:
                names = sorted(path.name for path in directory.glob(detector.pattern) if path.is_file())
                matches.extend((name, detector.confidence) for name in names)
            if matches:
                detections.append(
                    Detection(
                        profile=profile.id,
                        label=profile.label,
                        root=directory,
                        confidence=max(confidence for _name, confidence in matches),
                        evidence=tuple(sorted({name for name, _confidence in matches})),
                    )
                )

    # A root-level manifest normally represents nested projects of the same ecosystem
    # (for example npm workspaces or a .NET solution), so keep the shallowest match.
    selected: list[Detection] = []
    for detection in sorted(
        detections,
        key=lambda item: (len(item.root.relative_to(root).parts), item.profile, str(item.root)),
    ):
        if any(
            existing.profile == detection.profile
            and (existing.root == detection.root or existing.root in detection.root.parents)
            for existing in selected
        ):
            continue
        selected.append(detection)
    return sorted(selected, key=lambda item: (str(item.root), item.profile))


def requested_projects(
    root: Path, requested: Iterable[str], profiles: dict[str, Profile]
) -> list[Detection]:
    detections: list[Detection] = []
    for profile_id in requested:
        profile = profiles.get(profile_id)
        if profile is None:
            available = ", ".join(sorted(profiles))
            raise AgenticError(f"profile not found: {profile_id}; available profiles: {available}")
        detections.append(
            Detection(
                profile=profile.id,
                label=profile.label,
                root=root.resolve(),
                confidence=1.0,
                evidence=("explicit profile",),
            )
        )
    return detections


def build_quality_config(
    repository_root: Path,
    detections: list[Detection],
    profiles: dict[str, Profile],
) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    gates: list[dict[str, Any]] = []
    names: set[str] = set()
    for detection in detections:
        profile = profiles[detection.profile]
        source = _load_json(profile.config_path, f"quality configuration for {profile.id}")
        relative = detection.root.relative_to(repository_root)
        location = relative.as_posix() if relative.parts else "."
        for source_gate in source.get("gates", []):
            if not isinstance(source_gate, dict):
                raise AgenticError(f"profile {profile.id} contains an invalid gate")
            gate = copy.deepcopy(source_gate)
            original_name = gate.get("name")
            if not isinstance(original_name, str):
                raise AgenticError(f"profile {profile.id} contains a gate without a name")
            qualifier = profile.id if location == "." else f"{profile.id}@{location}"
            gate["name"] = f"{qualifier}/{original_name}"
            if gate["name"] in names:
                raise AgenticError(f"generated duplicate gate name: {gate['name']}")
            names.add(gate["name"])
            if location != ".":
                gate["working_directory"] = location
            gates.append(gate)
    return {
        "project": repository_root.name,
        "artifacts_dir": "artifacts",
        "gates": gates,
    }
