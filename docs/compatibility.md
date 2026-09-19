# Compatibility

The canonical source is `.agentic/constitution` plus `.agentic/skills`. `adapters sync` projects a thin
managed instruction block into the surfaces that exist in the repository:

One file per discipline, named `agentic-<id>`, plus an index where the surface reads one:

| Surface | Generated path |
|---|---|
| Canonical | `.agentic/constitution/CORE.md`, `.agentic/skills/<slug>/SKILL.md` (for example `01-source`) |
| Generic | `AGENTS.md` (index) |
| Claude Code | `.claude/skills/agentic-<id>/SKILL.md` |
| Cursor | `.cursor/rules/agentic-<id>.mdc` |
| Antigravity/Codex-style | `.agents/skills/agentic-<id>/SKILL.md` |
| Windsurf | `.windsurf/rules/agentic-<id>.md` |
| GitHub Copilot | `.github/instructions/agentic-<id>.instructions.md`, `.github/copilot-instructions.md` (index) |
| Gemini fallback | `GEMINI.md` (index) |

Adapters do not contain a second philosophy. Removing vendor directories leaves the canonical payload
and generic `AGENTS.md` usable offline.
