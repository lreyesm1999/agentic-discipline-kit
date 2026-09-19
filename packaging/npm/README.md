# agentic-discipline

Install engineering discipline for AI coding agents into any repository, with
one command and no runtime to manage.

```bash
npx agentic-discipline init
```

It detects the agent tools your repository already uses and writes each one's
native format:

| Tool | Receives |
|---|---|
| Claude Code | `.claude/skills/agentic-*/SKILL.md` |
| Cursor | `.cursor/rules/agentic-*.mdc`, scoped by `globs` |
| GitHub Copilot | `.github/instructions/agentic-*.instructions.md`, scoped by `applyTo` |
| Windsurf | `.windsurf/rules/agentic-*.md`, with trigger modes |
| Antigravity | `.agents/skills/agentic-*/SKILL.md` |
| Gemini CLI | `GEMINI.md` |
| Codex, Zed, Cline, Aider, Jules | `AGENTS.md` |
| ChatGPT | a paste-ready bundle |

All twelve disciplines are compiled from one canonical source, so the surfaces
cannot drift apart, and each carries the activation metadata its host tool needs.

Two files land in your repository root - `AGENTS.md` and `agentic.config.json`.
Everything else lives in `.agentic/`.

## Usage

```bash
npx agentic-discipline init --dry-run           # preview, write nothing
npx agentic-discipline init --adapter cursor    # emit a specific surface
npx agentic-discipline adapters list            # what the compiler supports
npx agentic-discipline adapters sync            # recompile after an update
npx agentic-discipline doctor --check-tools     # verify the installation
```

## The project control plane

The package also provides `agentic`, the Agentic Discipline 2 control plane: persistent
project knowledge, task contracts, checkpoints another agent can resume from, isolated
Git workspaces and verification evidence that goes stale when its inputs change.

```bash
npx -p agentic-discipline agentic adopt       # index this repository into .agentic/control
npx -p agentic-discipline agentic status      # knowledge, tasks, evidence at a glance
npx -p agentic-discipline agentic mcp         # stdio MCP server for your agent
```

Its trust boundary is one trusted user on a local filesystem; see
[LIMITATIONS.md](https://github.com/lreyesm1999/agentic-discipline-kit/blob/main/docs/v2/LIMITATIONS.md).

Each command reuses the same command already on your `PATH`, and
otherwise downloads the standalone build for your platform once and caches it
under `~/.cache/agentic-discipline`. Node 18 or newer. Standalone builds exist for
Linux x64 and Windows x64; on macOS and other platforms, install with pipx below.

Prefer Python? `pipx install agentic-discipline-kit` provides both commands.

Documentation: <https://github.com/lreyesm1999/agentic-discipline-kit>

MIT licensed.
