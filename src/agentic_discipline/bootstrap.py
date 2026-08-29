from __future__ import annotations

import json
import os
import shutil
import sys
import sysconfig
from pathlib import Path
from typing import Any, Iterable

from .common import AgenticError
from .profiles import (
    Detection,
    build_quality_config,
    detect_projects,
    load_profiles,
    requested_projects,
)

COPY_ITEMS = ["AGENTS.md", "MASTER_PROMPT.md", "skills", "policies", "schemas", "templates"]


def find_contract_root() -> Path:
    module_path = Path(__file__).resolve()
    candidates: list[Path] = []
    configured_root = os.environ.get("AGENTIC_DISCIPLINE_CONTRACT_ROOT")
    if configured_root:
        candidates.append(Path(configured_root).expanduser())
    candidates.extend(module_path.parents)
    candidates.extend(Path.cwd().parents)
    candidates.append(Path.cwd())
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        candidates.append(Path(frozen_root))
    candidates.append(Path(sysconfig.get_path("data")) / "share" / "agentic-discipline")
    seen: set[Path] = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        # Mutmut and similar tools may copy only part of the repository.  A
        # partial copy can contain AGENTS.md/skills but not the profile data;
        # require the complete contract bundle before accepting a candidate.
        if (
            (candidate / "AGENTS.md").is_file()
            and (candidate / "skills").is_dir()
            and (candidate / "config" / "profiles" / "generic.json").is_file()
        ):
            return candidate
    raise AgenticError("packaged Agentic Discipline contracts were not found")


def _copy_item(source: Path, target: Path, force: bool, actions: list[str]) -> None:
    if target.exists() and not force:
        actions.append(f"SKIP {target} (already exists)")
        return
    if source.is_dir():
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    actions.append(f"COPY {target}")


def _prepare_target(target: Path, kit_root: Path) -> Path:
    target_root = target.resolve()
    if target_root == Path(target_root.anchor):
        raise AgenticError("refusing to bootstrap into a filesystem root")
    module_path = Path(__file__).resolve()
    running_from_target = module_path.is_relative_to(target_root) and any(
        (target_root / package_root).is_dir()
        for package_root in (Path("src") / "agentic_discipline", Path("agentic_discipline"))
    )
    if target_root == kit_root or running_from_target:
        raise AgenticError("refusing to bootstrap the kit into itself")
    target_root.mkdir(parents=True, exist_ok=True)
    return target_root


def _write_quality_config(
    target: Path, config: dict[str, Any], force: bool, actions: list[str]
) -> None:
    output = target / "agentic.config.json"
    if output.exists() and not force:
        actions.append(f"SKIP {output} (already exists)")
        return
    output.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    actions.append(f"WRITE {output}")


def initialize_project(
    target: Path,
    profile_ids: Iterable[str] | None = None,
    profile_files: Iterable[Path] = (),
    force: bool = False,
    max_depth: int = 4,
) -> dict[str, Any]:
    kit_root = find_contract_root().resolve()
    target_root = _prepare_target(target, kit_root)
    profiles = load_profiles(kit_root, profile_files)
    requested = list(profile_ids or [])
    detections = (
        requested_projects(target_root, requested, profiles)
        if requested
        else detect_projects(target_root, profiles, max_depth=max_depth)
    )
    if not detections:
        generic = profiles["generic"]
        detections = [
            Detection(
                profile=generic.id,
                label=generic.label,
                root=target_root,
                confidence=0.0,
                evidence=("no known project manifest detected",),
            )
        ]

    actions: list[str] = []
    for item in COPY_ITEMS:
        _copy_item(kit_root / item, target_root / item, force, actions)

    config = build_quality_config(target_root, detections, profiles)
    _write_quality_config(target_root, config, force, actions)
    _copy_item(
        kit_root / "config" / "risk-weights.json",
        target_root / "config" / "risk-weights.json",
        force,
        actions,
    )

    for managed_dir in ("specs", "acceptance", "architecture", "artifacts", ".agent-memory"):
        directory = target_root / managed_dir
        directory.mkdir(parents=True, exist_ok=True)
        gitkeep = directory / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.write_text("", encoding="utf-8")

    gitignore = target_root / ".gitignore"
    marker = "# Agentic Discipline managed outputs"
    block = (
        f"\n{marker}\nartifacts/*\n!artifacts/.gitkeep\n.agent-memory/*\n!.agent-memory/.gitkeep\n"
    )
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    if marker not in existing:
        gitignore.write_text(existing.rstrip() + block, encoding="utf-8")
        actions.append(f"UPDATE {gitignore}")
    actions.append(f"READY {target_root}")
    return {
        "status": "PASS",
        "target": str(target_root),
        "profiles": [detection.profile for detection in detections],
        "detections": [detection.report(target_root) for detection in detections],
        "config": str(target_root / "agentic.config.json"),
        "actions": actions,
    }


def bootstrap_project(target: Path, stack: str | None = None, force: bool = False) -> list[str]:
    """Backward-compatible bootstrap wrapper.

    New callers should use ``initialize_project``. ``stack`` now selects a data-driven
    profile and is optional; omitting it enables automatic project detection.
    """

    result = initialize_project(
        target,
        profile_ids=[stack] if stack else None,
        force=force,
    )
    return list(result["actions"])
