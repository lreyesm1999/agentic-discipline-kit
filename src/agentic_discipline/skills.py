"""Canonical discipline source and its tool-neutral activation metadata.

Every agent-facing surface is compiled from the disciplines loaded here, so a
dialect emitter never invents content and the surfaces cannot drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .common import AgenticError

FRONTMATTER_FENCE = "---"
REQUIRED_KEYS = ("id", "name", "description")


@dataclass(frozen=True)
class Discipline:
    """One canonical discipline with the metadata every dialect needs."""

    id: str
    name: str
    title: str
    description: str
    when_to_use: str
    globs: tuple[str, ...]
    always: bool
    phase: str
    body: str
    slug: str = field(compare=False, default="")

    @property
    def glob_list(self) -> str:
        return ",".join(self.globs) if self.globs else "**"

    @property
    def summary(self) -> str:
        """Both halves in one string, for dialects with a single description field.

        Cursor, Windsurf and Copilot decide from one field, so dropping the
        trigger there would cost exactly the selectivity this metadata buys.
        """

        if not self.when_to_use:
            return self.description
        trigger = self.when_to_use
        for opener in ("When ", "Before ", "After ", "During "):
            if trigger.startswith(opener):
                # "When strengthening a change" reads as "Use when strengthening
                # a change", not "Use when: when strengthening a change".
                clause = f"Use {opener.lower()}{trigger[len(opener) :]}"
                break
        else:
            clause = f"Use when: {trigger[0].lower()}{trigger[1:]}"
        return f"{self.description} {clause}"


def _unquote(value: str) -> str:
    """Drop the surrounding quotes ``render_frontmatter`` adds, so a read of an
    emitted file returns the value that was written."""

    for quote in ("'", '"'):
        if len(value) >= 2 and value.startswith(quote) and value.endswith(quote):
            return value[1:-1]
    return value


def parse_frontmatter(text: str, label: str) -> tuple[dict[str, str], str]:
    """Split a leading ``---`` block into scalar keys plus the remaining body.

    Only the flat ``key: value`` subset this kit emits is supported, which keeps
    the package free of a YAML dependency.
    """

    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_FENCE:
        return {}, text
    metadata: dict[str, str] = {}
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == FRONTMATTER_FENCE:
            body = "\n".join(lines[index + 1 :]).lstrip("\n")
            return metadata, body
        if not line.strip():
            continue
        key, separator, value = line.partition(":")
        if not separator:
            raise AgenticError(f"invalid frontmatter line in {label}: {line!r}")
        metadata[key.strip()] = _unquote(value.strip())
    raise AgenticError(f"unterminated frontmatter in {label}")


def render_frontmatter(fields: dict[str, str]) -> str:
    """Serialize scalar frontmatter, quoting only what a YAML reader needs."""

    lines = [FRONTMATTER_FENCE]
    for key, value in fields.items():
        text = str(value)
        needs_quotes = text.startswith(("*", "[", "{", "&", "!", "#")) or ": " in text
        lines.append(f"{key}: {chr(39)}{text}{chr(39)}" if needs_quotes else f"{key}: {text}")
    lines.append(FRONTMATTER_FENCE)
    return "\n".join(lines) + "\n"


def load_discipline(path: Path) -> Discipline:
    metadata, body = parse_frontmatter(path.read_text(encoding="utf-8"), str(path))
    missing = [key for key in REQUIRED_KEYS if not metadata.get(key)]
    if missing:
        raise AgenticError(f"discipline {path} is missing frontmatter keys: {', '.join(missing)}")
    globs = tuple(item.strip() for item in metadata.get("globs", "**").split(",") if item.strip())
    # The title is carried in frontmatter, so an emitter owns the heading; keeping
    # the body's own `# Title` would render it twice on every surface.
    lines = body.strip().splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    return Discipline(
        id=metadata["id"],
        name=metadata["name"],
        title=metadata.get("title", metadata["id"].title()),
        description=metadata["description"],
        when_to_use=metadata.get("when_to_use", ""),
        globs=globs or ("**",),
        always=metadata.get("always", "false").lower() == "true",
        phase=metadata.get("phase", "implementation"),
        body="\n".join(lines).strip() + "\n",
        slug=path.parent.name,
    )


def load_disciplines(kit_root: Path) -> list[Discipline]:
    source = kit_root / "disciplines"
    if not source.is_dir():
        raise AgenticError(f"canonical disciplines not found: {source}")
    disciplines = [load_discipline(path) for path in sorted(source.glob("*/SKILL.md"))]
    if not disciplines:
        raise AgenticError(f"no disciplines found under {source}")
    duplicates = sorted({item.id for item in disciplines if _count(disciplines, item.id) > 1})
    if duplicates:
        raise AgenticError(f"duplicate discipline ids: {', '.join(duplicates)}")
    return disciplines


def _count(disciplines: list[Discipline], identifier: str) -> int:
    return sum(1 for item in disciplines if item.id == identifier)


def load_constitution(kit_root: Path) -> str:
    path = kit_root / "agentic" / "constitution" / "CORE.md"
    if not path.is_file():
        raise AgenticError(f"canonical constitution not found: {path}")
    return path.read_text(encoding="utf-8").rstrip() + "\n"
