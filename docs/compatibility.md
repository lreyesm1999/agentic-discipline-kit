# Compatibility

The canonical source is `.agentic/constitution` plus `.agentic/skills`. `adapters sync` projects a thin
managed instruction block into the surfaces that exist in the repository:

| Surface | Generated path |
|---|---|
| Generic | `AGENTS.md` |
| Claude Code | `.claude/skills/agentic-discipline/SKILL.md` |
| Cursor | `.cursor/rules/agentic-discipline.mdc` |
| Antigravity/Codex-style | `.agents/skills/agentic-discipline/SKILL.md` |
| Windsurf | `.windsurf/rules/agentic-discipline.md` |
| GitHub Copilot | `.github/copilot-instructions.md` |
| Gemini fallback | `GEMINI.md` |

Adapters do not contain a second philosophy. Removing vendor directories leaves the canonical payload
and generic `AGENTS.md` usable offline.
