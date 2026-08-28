from __future__ import annotations

import shutil
import sysconfig
from pathlib import Path

from .common import AgenticError

COPY_ITEMS = ["AGENTS.md", "MASTER_PROMPT.md", "skills", "policies", "schemas", "templates"]
STACKS = {"typescript", "python", "dotnet"}


def find_contract_root() -> Path:
    candidates = [
        Path(__file__).resolve().parents[2],
        Path(sysconfig.get_path("data")) / "share" / "agentic-discipline",
    ]
    for candidate in candidates:
        if (candidate / "AGENTS.md").is_file() and (candidate / "skills").is_dir():
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


def bootstrap_project(target: Path, stack: str, force: bool = False) -> list[str]:
    if stack not in STACKS:
        raise AgenticError(f"unsupported stack: {stack}")
    kit_root = find_contract_root().resolve()
    target_root = target.resolve()
    if target_root == Path(target_root.anchor):
        raise AgenticError("refusing to bootstrap into a filesystem root")
    if target_root == kit_root:
        raise AgenticError("refusing to bootstrap the kit into itself")
    target_root.mkdir(parents=True, exist_ok=True)

    actions: list[str] = []
    for item in COPY_ITEMS:
        _copy_item(kit_root / item, target_root / item, force, actions)

    config_source = kit_root / "config" / "examples" / f"{stack}.json"
    _copy_item(config_source, target_root / "agentic.config.json", force, actions)
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
    return actions
