from __future__ import annotations

import json
import os
import shutil
import sqlite3
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


CONTROL_DIRECTORY = ".agentic/control"

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
    end = marker_at + 1
    while end < len(lines) and lines[end].strip():
        end += 1
    updated = [*lines[:end], *missing, *lines[end:]]
    _write_gitignore(gitignore, newline.join(updated) + newline, dry_run)
    actions.append(f"UPDATE {gitignore} (added {', '.join(missing)})")


def _read_gitignore(gitignore: Path) -> str:
    return gitignore.read_bytes().decode("utf-8") if gitignore.exists() else ""


def _write_gitignore(gitignore: Path, content: str, dry_run: bool) -> None:
    if not dry_run:
        gitignore.write_bytes(content.encode("utf-8"))


def _control_mode_for(target_root: Path, *, rules_only: bool, adopt: bool | None) -> str:
    """`rules-only` is a decision, and init does not quietly reverse one.

    A project that recorded it keeps it until someone asks for the control plane by name,
    because the alternative is that a routine re-run turns orchestration on behind their
    back. `adopt` is None for an ordinary run, True for `--adopt`, False for `--no-adopt`.
    """

    from .readiness import STATE_DB, control_mode

    # An existing state database settles the question: the project is managed, whatever was
    # recorded before. Recording rules-only cannot un-adopt it, because removing the state
    # is the owner's decision rather than the side effect of an install flag.
    if (target_root / STATE_DB).is_file():
        return "managed"
    if rules_only:
        return "rules-only"
    if adopt:
        return "managed"
    return control_mode(target_root)


def _set_control_mode(target_root: Path, mode: str, actions: list[str], dry_run: bool) -> None:
    """Record the mode in the payload config without disturbing the rest of it."""

    path = target_root / ".agentic" / "config.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if payload.get("control", {}).get("mode") == mode:
        return
    if not dry_run:
        path.write_text(
            json.dumps({**payload, "control": {"mode": mode}}, indent=2) + "\n", encoding="utf-8"
        )
    actions.append(f"UPDATE {path} (control mode {mode})")


def _control_phase(
    target_root: Path,
    *,
    mode: str,
    adopt: bool | None,
    rules_only: bool,
    actions: list[str],
    dry_run: bool,
) -> dict[str, Any]:
    """Make the control plane operational, or say exactly why it was left alone.

    Adoption inspects the repository and records state; it never edits the project's own
    files, installs anything, or runs instructions it finds in the tree.
    """

    from .control.plane import Plane
    from .control.plane import adopt as adopt_project
    from .readiness import STATE_DB

    if rules_only and mode != "rules-only":
        return {
            "status": "REFUSED",
            "detail": "this project is already adopted, so --rules-only was not recorded:"
            " the existing tasks, leases and evidence stay, and removing"
            f" {CONTROL_DIRECTORY} is yours to decide",
            "repair": None,
        }
    if mode == "rules-only":
        return {
            "status": "SKIPPED",
            "detail": "installed rules-only, so the control plane was not initialised",
            "repair": "agentic-discipline init --adopt",
        }
    if adopt is False:
        return {
            "status": "SKIPPED",
            "detail": "--no-adopt was given, so the control plane was left as it is",
            "repair": "agentic adopt",
        }
    if dry_run:
        return {
            "status": "PENDING",
            "detail": "would adopt the repository and index the project",
            "repair": None,
        }
    already = (target_root / STATE_DB).is_file()
    try:
        adopt_project(target_root)
    except (AgenticError, sqlite3.Error) as exc:
        # An unexplained control directory is the one case adoption must not resolve on its
        # own: a second database beside it would split the project's history in two.
        return {"status": "BLOCKED", "detail": str(exc), "repair": None}
    if not already:
        actions.append(f"ADOPT {target_root / STATE_DB}")
        return {"status": "ADOPTED", "detail": "the repository was adopted and indexed"}
    # Re-running init on an adopted project keeps every task, lease, checkpoint and piece of
    # evidence: the knowledge index is brought up to date and nothing else is touched.
    with Plane(target_root) as plane:
        reconciled = plane.reconcile()
    changed = len(cast(list[object], reconciled.get("changed_paths", [])))
    actions.append(f"RECONCILE {target_root / STATE_DB} ({changed} paths)")
    return {
        "status": "KEPT",
        "detail": f"already adopted; the index was reconciled over {changed} changed path(s)",
    }


def initialize_project(
    target: Path,
    profile_ids: Iterable[str] | None = None,
    profile_files: Iterable[Path] = (),
    force: bool = False,
    max_depth: int = 4,
    adapters: Iterable[str] | None = None,
    dry_run: bool = False,
    adopt: bool | None = None,
    rules_only: bool = False,
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

    mode = _control_mode_for(target_root, rules_only=rules_only, adopt=adopt)
    _set_control_mode(target_root, mode, actions, dry_run)
    control = _control_phase(
        target_root,
        mode=mode,
        adopt=adopt,
        rules_only=rules_only,
        actions=actions,
        dry_run=dry_run,
    )
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
    # The verdict is measured, not assumed: what init reports as ready is whatever the
    # readiness checks find after it has finished writing. A dry run has written nothing,
    # so there is nothing to measure.
    from . import readiness

    report = None if dry_run else readiness.inspect(target_root)
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
        "control_mode": mode,
        "control": control,
        "readiness": report,
        "actions": actions,
    }
