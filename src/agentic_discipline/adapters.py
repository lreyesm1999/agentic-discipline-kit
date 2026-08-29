from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .bootstrap import find_contract_root

ADAPTERS = {
    "generic": "AGENTS.md",
    "claude": ".claude/skills/agentic-discipline/SKILL.md",
    "cursor": ".cursor/rules/agentic-discipline.mdc",
    "antigravity": ".agents/skills/agentic-discipline/SKILL.md",
    "windsurf": ".windsurf/rules/agentic-discipline.md",
    "copilot": ".github/copilot-instructions.md",
    "gemini": "GEMINI.md",
}
MANAGED_START = "<!-- agentic-discipline:managed:start -->"
MANAGED_END = "<!-- agentic-discipline:managed:end -->"


def detect_adapters(project_root: Path) -> list[str]:
    root = project_root.resolve()
    detected = ["generic"]
    markers = {
        "claude": root / ".claude",
        "cursor": root / ".cursor",
        "antigravity": root / ".agents",
        "windsurf": root / ".windsurf",
        "copilot": root / ".github",
        "gemini": root / "GEMINI.md",
    }
    detected.extend(name for name, marker in markers.items() if marker.exists())
    return detected


def _canonical_body(kit_root: Path) -> str:
    core = (kit_root / "agentic" / "constitution" / "CORE.md").read_text(encoding="utf-8")
    return f"{MANAGED_START}\n\n# Agentic Discipline\n\nRead the canonical constitution at `.agentic/constitution/CORE.md` and activate the relevant skill under `.agentic/skills/`.\n\n{core}\n\n{MANAGED_END}\n"


def _sync_file(path: Path, body: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if MANAGED_START in existing and MANAGED_END in existing:
        start = existing.index(MANAGED_START)
        end = existing.index(MANAGED_END, start) + len(MANAGED_END)
        updated = existing[:start] + body.rstrip() + existing[end:]
    else:
        updated = existing.rstrip() + ("\n\n" if existing.strip() else "") + body
    if updated != existing:
        path.write_text(updated.rstrip() + "\n", encoding="utf-8")
        return f"UPDATE {path}"
    return f"SKIP {path} (already synchronized)"


def sync_adapters(project_root: Path, adapter_names: Iterable[str] | None = None) -> dict[str, object]:
    root = project_root.resolve()
    kit_root = find_contract_root()
    names = list(adapter_names) if adapter_names is not None else detect_adapters(root)
    unknown = sorted(set(names) - set(ADAPTERS))
    if unknown:
        raise ValueError(f"unknown adapters: {', '.join(unknown)}")
    skills_source = kit_root / "disciplines"
    if not skills_source.is_dir():
        raise FileNotFoundError(f"canonical disciplines not found: {skills_source}")
    actions: list[str] = []
    target_skills = root / ".agentic" / "skills"
    for source in sorted(skills_source.glob("*/SKILL.md")):
        destination = target_skills / source.parent.name / "SKILL.md"
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = source.read_text(encoding="utf-8")
        if not destination.exists() or destination.read_text(encoding="utf-8") != content:
            destination.write_text(content, encoding="utf-8")
            actions.append(f"COPY {destination}")
    body = _canonical_body(kit_root)
    for name in names:
        relative = ADAPTERS[name]
        actions.append(_sync_file(root / relative, body))
    return {"status": "PASS", "adapters": names, "actions": actions}
