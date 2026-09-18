"""Compile the canonical disciplines into each agent tool's native dialect.

Every surface is generated from ``disciplines/`` so the tools cannot drift, but
each one is emitted in the format that tool actually loads: skills with a
separate ``when_to_use`` field for Claude Code, ``globs``-scoped rules for
Cursor, ``applyTo`` instructions for Copilot, and plain ``AGENTS.md`` for the
growing set of tools that converge on it.

A dialect with only one description field receives ``Discipline.summary``, which
folds the trigger back into that field; dropping it there would cost exactly the
selective activation the metadata exists to buy.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from . import __version__
from .bootstrap import find_contract_root
from .common import AgenticError
from .skills import Discipline, load_constitution, load_disciplines, render_frontmatter

MANAGED_START = "<!-- agentic-discipline:managed:start -->"
MANAGED_END = "<!-- agentic-discipline:managed:end -->"
GENERATED_PREFIX = "agentic-"

# Tools that read a file another target already owns are aliases, not dialects:
# emitting twice into one path would make the last writer win silently.
ALIASES = {
    "codex": "generic",
    "chatgpt-codex": "generic",
    "zed": "generic",
    "cline": "generic",
    "roo": "generic",
    "aider": "generic",
    "jules": "generic",
}


@dataclass
class Emission:
    """Collects filesystem intent so ``--dry-run`` shares one code path."""

    dry_run: bool = False

    def __post_init__(self) -> None:
        self.actions: list[str] = []

    def write(self, path: Path, content: str) -> None:
        if path.exists() and path.read_text(encoding="utf-8") == content:
            self.actions.append(f"SKIP {path} (already synchronized)")
            return
        verb = "UPDATE" if path.exists() else "WRITE"
        if not self.dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        self.actions.append(f"{verb} {path}")

    def write_managed(self, path: Path, block: str) -> None:
        """Replace only the managed region so user-authored content survives."""

        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        body = f"{MANAGED_START}\n\n{block.rstrip()}\n\n{MANAGED_END}"
        if MANAGED_START in existing and MANAGED_END in existing:
            start = existing.index(MANAGED_START)
            end = existing.index(MANAGED_END, start) + len(MANAGED_END)
            updated = existing[:start] + body + existing[end:]
        else:
            updated = existing.rstrip() + ("\n\n" if existing.strip() else "") + body
        self.write(path, updated.rstrip() + "\n")

    def prune(self, directory: Path, keep: set[Path]) -> None:
        """Remove previously generated files for disciplines that no longer exist."""

        if not directory.is_dir():
            return
        for path in sorted(directory.glob(f"{GENERATED_PREFIX}*")):
            resolved = path / "SKILL.md" if path.is_dir() else path
            if resolved in keep:
                continue
            if not self.dry_run:
                if path.is_dir():
                    for child in sorted(path.rglob("*"), reverse=True):
                        if child.is_file():
                            child.unlink()
                        else:
                            child.rmdir()
                    path.rmdir()
                else:
                    path.unlink()
            self.actions.append(f"REMOVE {resolved} (stale)")


def _rules(core: str) -> str:
    """The constitution without its own title, so it can sit under any heading."""

    lines = core.strip().splitlines()
    if lines and lines[0].startswith("#"):
        lines = lines[1:]
    return "\n".join(lines).strip()


def _skill_frontmatter(discipline: Discipline) -> dict[str, str]:
    """Frontmatter for formats that carry the trigger in its own field."""

    fields = {"name": discipline.name, "description": discipline.description}
    if discipline.when_to_use:
        fields["when_to_use"] = discipline.when_to_use
    return fields


def _skill_document(discipline: Discipline, core: str) -> str:
    """The portable body shared by every per-discipline surface."""

    return (
        f"# {discipline.title}\n\n"
        f"{discipline.description}\n\n"
        f"**When to use.** {discipline.when_to_use or 'See the trigger conditions below.'}\n\n"
        f"{discipline.body.rstrip()}\n\n"
        "## Non-negotiables\n\n"
        f"{_rules(core)}\n\n"
        "## Deterministic checks\n\n"
        "Measurable claims are proved by execution, not narration. When the CLI is available:\n\n"
        "```bash\n"
        "agentic-discipline quality --config agentic.config.json\n"
        "agentic-discipline verify <VERIFIER-ID>\n"
        "```\n"
    )


def _index(disciplines: list[Discipline], core: str, location: str) -> str:
    rows = "\n".join(f"- **{item.title}** (`{item.name}`) - {item.summary}" for item in disciplines)
    return (
        "# Agentic Discipline\n\n"
        "## Non-negotiables\n\n"
        f"{_rules(core)}\n\n"
        "## Disciplines\n\n"
        f"{rows}\n\n"
        f"The full text of each discipline lives in `{location}`.\n"
    )


def _emit_per_discipline(
    emission: Emission,
    directory: Path,
    disciplines: list[Discipline],
    core: str,
    frontmatter: Callable[[Discipline], dict[str, str]],
    *,
    nested: bool,
    suffix: str = ".md",
) -> None:
    written: set[Path] = set()
    for discipline in disciplines:
        stem = f"{GENERATED_PREFIX}{discipline.id}"
        path = directory / stem / "SKILL.md" if nested else directory / f"{stem}{suffix}"
        emission.write(
            path,
            render_frontmatter(frontmatter(discipline)) + "\n" + _skill_document(discipline, core),
        )
        written.add(path)
    emission.prune(directory, written)


def _emit_canonical(
    emission: Emission, root: Path, disciplines: list[Discipline], core: str
) -> None:
    """Install the vendor-neutral source every dialect points back to.

    Emitted on every sync so ``adapters sync`` works on a repository that was
    never initialized, and stays idempotent when it was.
    """

    emission.write(root / ".agentic" / "constitution" / "CORE.md", core)
    for discipline in disciplines:
        emission.write(
            root / ".agentic" / "skills" / discipline.slug / "SKILL.md",
            _skill_document(discipline, core),
        )


def _emit_generic(emission: Emission, root: Path, disciplines: list[Discipline], core: str) -> None:
    """AGENTS.md: the convention Codex, Zed, Cline, Aider and others all read."""

    emission.write_managed(root / "AGENTS.md", _index(disciplines, core, ".agentic/skills/"))


def _emit_claude(emission: Emission, root: Path, disciplines: list[Discipline], core: str) -> None:
    _emit_per_discipline(
        emission,
        root / ".claude" / "skills",
        disciplines,
        core,
        _skill_frontmatter,
        nested=True,
    )


def _emit_antigravity(
    emission: Emission, root: Path, disciplines: list[Discipline], core: str
) -> None:
    _emit_per_discipline(
        emission,
        root / ".agents" / "skills",
        disciplines,
        core,
        _skill_frontmatter,
        nested=True,
    )


def _emit_cursor(emission: Emission, root: Path, disciplines: list[Discipline], core: str) -> None:
    _emit_per_discipline(
        emission,
        root / ".cursor" / "rules",
        disciplines,
        core,
        lambda item: {
            "description": item.summary,
            "globs": item.glob_list,
            "alwaysApply": "true" if item.always else "false",
        },
        nested=False,
        suffix=".mdc",
    )


def _emit_windsurf(
    emission: Emission, root: Path, disciplines: list[Discipline], core: str
) -> None:
    _emit_per_discipline(
        emission,
        root / ".windsurf" / "rules",
        disciplines,
        core,
        lambda item: {
            "trigger": "always_on" if item.always else "glob",
            "description": item.summary,
            "globs": item.glob_list,
        },
        nested=False,
    )


def _emit_copilot(emission: Emission, root: Path, disciplines: list[Discipline], core: str) -> None:
    _emit_per_discipline(
        emission,
        root / ".github" / "instructions",
        disciplines,
        core,
        lambda item: {"description": item.summary, "applyTo": item.glob_list},
        nested=False,
        suffix=".instructions.md",
    )
    emission.write_managed(
        root / ".github" / "copilot-instructions.md",
        _index(disciplines, core, ".github/instructions/"),
    )


def _emit_gemini(emission: Emission, root: Path, disciplines: list[Discipline], core: str) -> None:
    emission.write_managed(root / "GEMINI.md", _index(disciplines, core, ".agentic/skills/"))


def _emit_chatgpt(emission: Emission, root: Path, disciplines: list[Discipline], core: str) -> None:
    """ChatGPT has no project filesystem, so ship one paste-ready bundle."""

    sections = "\n\n---\n\n".join(
        f"## {item.title}\n\n{item.summary}\n\n{item.body.rstrip()}" for item in disciplines
    )
    emission.write(
        root / ".agentic" / "export" / "chatgpt" / "agentic-discipline.md",
        (
            "# Agentic Discipline - ChatGPT bundle\n\n"
            "Paste this into a ChatGPT Project instruction field or a Custom GPT's "
            "instructions. Codex reads `AGENTS.md` directly and needs no bundle.\n\n"
            "## Non-negotiables\n\n"
            f"{_rules(core)}\n\n{sections}\n"
        ),
    )


# The lifecycle the kit has always documented, expressed as slash commands so a
# newcomer has a visible entry point instead of a folder of markdown. The third
# element is the argument hint the host shows while the user is typing.
COMMANDS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "execute",
        "Execute an authorized plan across tasks until completion or a real blocker.",
        "[plan path or requested scope]",
        ("autonomous-project-execution",),
    ),
    (
        "spec",
        "Turn a request into observable behavior and acceptance criteria.",
        "[request or requirement id]",
        ("source", "specification"),
    ),
    (
        "plan",
        "Break approved specification into the smallest coherent slices.",
        "[spec id]",
        ("specification", "acceptance"),
    ),
    (
        "risk",
        "Classify the change as LOW, STANDARD, HIGH or CRITICAL.",
        "[base ref]",
        ("source", "verification"),
    ),
    (
        "build",
        "Implement the current slice against approved acceptance.",
        "[task id]",
        ("coding",),
    ),
    (
        "test",
        "Prove the slice with executable verification.",
        "[task or verifier id]",
        ("verification", "qa"),
    ),
    (
        "harden",
        "Apply property, mutation, security and integrity pressure.",
        "[path or area]",
        ("hardening", "architecture"),
    ),
    (
        "review",
        "Review the change independently of the implementation agent.",
        "[base ref]",
        ("cleaning", "architecture"),
    ),
    (
        "verify",
        "Execute registered verifiers and record normalized results.",
        "[verifier id]",
        ("verification", "evidence"),
    ),
    (
        "release",
        "Assemble the evidence a release decision needs.",
        "[version]",
        ("evidence", "qa"),
    ),
    (
        "retro",
        "Record what the workflow should do differently next time.",
        "[scope]",
        ("evolution",),
    ),
)


def _emit_claude_plugin(
    emission: Emission, root: Path, disciplines: list[Discipline], core: str
) -> None:
    """Build the installable Claude Code plugin from the canonical source.

    Generated rather than hand-maintained so the marketplace copy can never
    drift from `disciplines/`.
    """

    by_id = {item.id: item for item in disciplines}
    emission.write(
        root / ".claude-plugin" / "plugin.json",
        json.dumps(
            {
                "name": "agentic-discipline",
                "description": (
                    "Evidence-backed engineering discipline for AI coding agents: "
                    "requirements, acceptance, verification, hardening, and release evidence."
                ),
                "version": __version__,
                "author": {"name": "Agentic Discipline Kit Contributors"},
                "homepage": "https://github.com/lreyesm1999/agentic-discipline-kit",
                "license": "MIT",
                "keywords": ["quality-gates", "verification", "acceptance-testing", "evidence"],
            },
            indent=2,
        )
        + "\n",
    )
    _emit_per_discipline(
        emission,
        root / "skills",
        disciplines,
        core,
        _skill_frontmatter,
        nested=True,
    )
    for name, summary, argument_hint, discipline_ids in COMMANDS:
        referenced = [by_id[item] for item in discipline_ids if item in by_id]
        steps = "\n".join(
            f"{index}. Apply **{item.title}** (`{item.name}`): {item.description}"
            for index, item in enumerate(referenced, start=1)
        )
        emission.write(
            root / "commands" / f"{name}.md",
            render_frontmatter({"description": summary, "argument-hint": argument_hint})
            + "\n"
            + f"# /{name}\n\n{summary}\n\n## Steps\n\n{steps}\n\n"
            "## Stop conditions\n\n"
            f"{_rules(core)}\n\n"
            "Report `UNKNOWN` or `BLOCKED` rather than presenting an unproven claim as `PASS`.\n",
        )


Emitter = Callable[[Emission, Path, list[Discipline], str], None]

EMITTERS: dict[str, Emitter] = {
    "generic": _emit_generic,
    "claude": _emit_claude,
    "cursor": _emit_cursor,
    "antigravity": _emit_antigravity,
    "windsurf": _emit_windsurf,
    "copilot": _emit_copilot,
    "gemini": _emit_gemini,
    "chatgpt": _emit_chatgpt,
    "claude-plugin": _emit_claude_plugin,
}

# Packaging targets build a distributable, not a project surface, so they never
# receive the `.agentic/` payload.
PACKAGING_TARGETS = {"claude-plugin"}

LABELS = {
    "generic": "AGENTS.md (Codex, Zed, Cline, Aider, Jules)",
    "claude": "Claude Code",
    "cursor": "Cursor",
    "antigravity": "Antigravity",
    "windsurf": "Windsurf",
    "copilot": "GitHub Copilot",
    "gemini": "Gemini CLI",
    "chatgpt": "ChatGPT (paste bundle)",
    "claude-plugin": "Claude Code plugin (packaging)",
}

MARKERS = {
    "claude": ".claude",
    "cursor": ".cursor",
    "antigravity": ".agents",
    "windsurf": ".windsurf",
    "copilot": ".github",
    "gemini": "GEMINI.md",
}

# One representative output per tool, as `adapters list` reports it. The emitters
# decide what is written; a test keeps each entry pointing at a path they produce.
ADAPTERS = {
    "generic": "AGENTS.md",
    "claude": ".claude/skills/",
    "cursor": ".cursor/rules/",
    "antigravity": ".agents/skills/",
    "windsurf": ".windsurf/rules/",
    "copilot": ".github/instructions/",
    "gemini": "GEMINI.md",
    "chatgpt": ".agentic/export/chatgpt/agentic-discipline.md",
    "claude-plugin": ".claude-plugin/plugin.json",
}


def resolve_adapters(names: Iterable[str]) -> list[str]:
    """Map aliases onto their dialect and drop duplicates, preserving order."""

    resolved: list[str] = []
    unknown: list[str] = []
    for name in names:
        target = ALIASES.get(name, name)
        if target not in EMITTERS:
            unknown.append(name)
        elif target not in resolved:
            resolved.append(target)
    if unknown:
        available = ", ".join(sorted(set(EMITTERS) | set(ALIASES)))
        raise ValueError(f"unknown adapters: {', '.join(sorted(unknown))}; available: {available}")
    return resolved


def detect_adapters(project_root: Path) -> list[str]:
    """AGENTS.md is always emitted; other dialects follow the tool's own marker."""

    root = project_root.resolve()
    detected = ["generic"]
    detected.extend(name for name, marker in MARKERS.items() if (root / marker).exists())
    return detected


def sync_adapters(
    project_root: Path,
    adapter_names: Iterable[str] | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    root = project_root.resolve()
    kit_root = find_contract_root()
    disciplines = load_disciplines(kit_root)
    core = load_constitution(kit_root)
    requested = list(adapter_names) if adapter_names is not None else detect_adapters(root)
    if not requested:
        raise AgenticError("no adapters selected")
    names = resolve_adapters(requested)

    emission = Emission(dry_run=dry_run)
    if not set(names) <= PACKAGING_TARGETS:
        _emit_canonical(emission, root, disciplines, core)
    for name in names:
        EMITTERS[name](emission, root, disciplines, core)

    return {
        "status": "PASS",
        "adapters": names,
        "labels": [LABELS[name] for name in names],
        "disciplines": [item.name for item in disciplines],
        "dry_run": dry_run,
        "actions": emission.actions,
    }
