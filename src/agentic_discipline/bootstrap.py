from __future__ import annotations

import json
import os
import shutil
import sys
import sysconfig
from pathlib import Path
from typing import Any, Iterable, cast

from .common import AgenticError
from .profiles import (
    Detection,
    annotate_gate_availability,
    build_quality_config,
    detect_projects,
    load_profiles,
    requested_projects,
)

# The kit installs into `.agentic/` so an adopting repository keeps its root:
# only AGENTS.md and agentic.config.json stay visible, the way `.github/` does.
PAYLOAD = {
    "MASTER_PROMPT.md": ".agentic/MASTER_PROMPT.md",
    "skills": ".agentic/playbooks",
    "policies": ".agentic/policies",
    "schemas": ".agentic/schemas",
    "templates": ".agentic/templates",
    "config/risk-weights.json": ".agentic/config/risk-weights.json",
}

# Directories such as `specs/`, `acceptance/` and `artifacts/` are created on
# demand by the phase that needs them; pre-creating them littered an adopting
# repository with `.gitkeep` files for phases a project may never reach.


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
    for candidate in candidates:
        candidate = candidate.resolve()
        # Mutmut and similar tools may copy only part of the repository.  A
        # partial copy can contain AGENTS.md/skills but not the profile data;
        # require the complete contract bundle before accepting a candidate.
        if (
            (candidate / "AGENTS.md").is_file()
            and (candidate / "disciplines").is_dir()
            and (candidate / "config" / "profiles" / "generic.json").is_file()
        ):
            return candidate
    raise AgenticError("packaged Agentic Discipline contracts were not found")


def _copy_item(
    source: Path, target: Path, force: bool, actions: list[str], dry_run: bool = False
) -> None:
    if target.exists() and not force:
        actions.append(f"SKIP {target} (already exists)")
        return
    if not dry_run:
        if source.is_dir():
            if target.exists():
                shutil.rmtree(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    actions.append(f"COPY {target}")


def _prepare_target(target: Path, kit_root: Path, dry_run: bool) -> Path:
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
    if not dry_run:
        target_root.mkdir(parents=True, exist_ok=True)
    return target_root


def _write_json(
    path: Path, payload: dict[str, Any], force: bool, actions: list[str], dry_run: bool
) -> None:
    if path.exists() and not force:
        actions.append(f"SKIP {path} (already exists)")
        return
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    actions.append(f"WRITE {path}")


def _install_payload(
    kit_root: Path, target_root: Path, force: bool, actions: list[str], dry_run: bool
) -> None:
    """Install the vendor-neutral payload under `.agentic/`."""

    for source_name, destination_name in PAYLOAD.items():
        source = kit_root / source_name
        if not source.exists():
            continue
        _copy_item(source, target_root / destination_name, force, actions, dry_run)

    verification = target_root / ".agentic" / "verification"
    if not dry_run:
        for directory in (verification, verification / "generated", verification / "artifacts"):
            directory.mkdir(parents=True, exist_ok=True)
    _write_json(
        verification / "registry.json",
        {"schema_version": "1", "verifiers": []},
        force,
        actions,
        dry_run,
    )
    _write_json(
        target_root / ".agentic" / "config.json",
        {
            "schema_version": "3",
            "adk": {"risk_default": "STANDARD", "unknown_blocks_release": True},
            "agents": {"mode": "auto", "adapters": ["generic"]},
            "verification": {
                "root": ".agentic/verification",
                "generated_root": ".agentic/verification/generated",
                "require_sensitivity_for_generated": True,
                "protect_validated_verifiers": True,
                "default_timeout_seconds": 120,
            },
            "evidence": {"root": "artifacts/agentic", "hash": "sha256"},
        },
        force,
        actions,
        dry_run,
    )


MANAGED_MARKER = "# Agentic Discipline managed outputs"
MANAGED_ENTRIES = (
    "artifacts/",
    ".agent-memory/",
    ".agentic/verification/artifacts/",
    ".agentic/export/",
    # The control plane's SQLite state and evidence belong to the checkout, not to
    # history: committing them shares one database, its hashes and its sessions.
    ".agentic/control/",
)


def _update_gitignore(target_root: Path, actions: list[str], dry_run: bool) -> None:
    gitignore = target_root / ".gitignore"
    # The file is read and written as bytes: text mode reads CRLF as LF and writes it back
    # as the platform's ending, so running this on Windows would rewrite every line of an
    # LF .gitignore. Keeping the bytes keeps the project's endings, and the block below is
    # written with the ones the file already uses.
    existing = _read_gitignore(gitignore)
    lines = existing.splitlines()
    newline = "\r\n" if "\r\n" in existing else "\n"
    marker_at = next((at for at, line in enumerate(lines) if MANAGED_MARKER in line), None)

    if marker_at is None:
        block = newline.join([MANAGED_MARKER, *MANAGED_ENTRIES])
        _write_gitignore(gitignore, existing.rstrip() + newline + block + newline, dry_run)
        actions.append(f"UPDATE {gitignore}")
        return

    # A project adopted before a release that added a rule has the marker but not the rule,
    # so the thing the rule keeps out of history is being committed until someone notices.
    # Add what is missing to the block this command owns, and leave the rest of the file.
    ignored = {line.strip() for line in lines}
    missing = [entry for entry in MANAGED_ENTRIES if entry not in ignored]
    if not missing:
        actions.append(f"SKIP {gitignore} (already configured)")
        return
    # The block runs to its first blank line, or to the end of the file. Found with a bounded
    # search rather than a hand-stepped loop, so no slip in the stepping can run forever.
    end = next((at for at in range(marker_at + 1, len(lines)) if not lines[at].strip()), len(lines))
    updated = [*lines[:end], *missing, *lines[end:]]
    _write_gitignore(gitignore, newline.join(updated) + newline, dry_run)
    actions.append(f"UPDATE {gitignore} (added {', '.join(missing)})")


def _read_gitignore(gitignore: Path) -> str:
    return gitignore.read_bytes().decode("utf-8") if gitignore.exists() else ""


def _write_gitignore(gitignore: Path, content: str, dry_run: bool) -> None:
    if not dry_run:
        gitignore.write_bytes(content.encode("utf-8"))


def initialize_project(
    target: Path,
    profile_ids: Iterable[str] | None = None,
    profile_files: Iterable[Path] = (),
    force: bool = False,
    max_depth: int = 4,
    adapters: Iterable[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    kit_root = find_contract_root().resolve()
    target_root = _prepare_target(target, kit_root, dry_run)
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
    _install_payload(kit_root, target_root, force, actions, dry_run)

    config = annotate_gate_availability(
        target_root, build_quality_config(target_root, detections, profiles)
    )
    _write_json(target_root / "agentic.config.json", config, force, actions, dry_run)
    _update_gitignore(target_root, actions, dry_run)

    from .adapters import detect_adapters, sync_adapters

    selected = list(adapters) if adapters is not None else detect_adapters(target_root)
    adapter_result = sync_adapters(target_root, selected, dry_run=dry_run)
    actions.extend(str(action) for action in cast(list[object], adapter_result["actions"]))
    actions.append(f"READY {target_root}")

    # A gate carrying a note was either relaxed or added; only the relaxed ones
    # are a caveat the reader has to act on.
    relaxed = [
        {"name": gate["name"], "note": gate["note"]}
        for gate in config["gates"]
        if isinstance(gate, dict) and "note" in gate and not gate.get("required", True)
    ]
    baseline = next(
        (
            gate["name"]
            for gate in config["gates"]
            if isinstance(gate, dict) and str(gate.get("note")).startswith("added by init")
        ),
        None,
    )
    return {
        "status": "PASS",
        "target": str(target_root),
        "dry_run": dry_run,
        "profiles": [detection.profile for detection in detections],
        "detections": [detection.report(target_root) for detection in detections],
        "config": str(target_root / "agentic.config.json"),
        "adapters": adapter_result["adapters"],
        "adapter_labels": adapter_result["labels"],
        "disciplines": adapter_result["disciplines"],
        "gates": len(config["gates"]),
        "relaxed_gates": relaxed,
        "baseline_gate": baseline,
        "actions": actions,
    }
