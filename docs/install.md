# Install

One command installs the disciplines into whichever agent tools your repository
already uses. Nothing else is required to start - the Python CLI is only needed
later, for the deterministic gates in CI.

## The one command

```bash
npx agentic-discipline init
```

It detects the tools present in the repository and writes each one's native
format. Run it from the repository root. Node 18+ is the only requirement; the
launcher reuses an `agentic-discipline` already on your `PATH` and otherwise
downloads the standalone build for your platform once and caches it.

Preview it first if you prefer:

```bash
npx agentic-discipline init --dry-run
```

## What lands in your repository

```text
AGENTS.md              read by Codex, Zed, Cline, Aider, Jules and others
agentic.config.json    quality gates, generated for your stack
.agentic/              everything else: disciplines, playbooks, policies, schemas
```

Two visible files. Everything else lives in `.agentic/`, the way tooling
belongs in `.github/`. Directories for specs, acceptance and artifacts are
created by the phase that needs them, not up front.

## Per-tool install

| Tool | Install | What it receives |
|---|---|---|
| Claude Code | `/plugin marketplace add lreyesm1999/agentic-discipline-kit` then `/plugin install agentic-discipline@agentic-discipline-kit` | 11 skills plus `/spec` through `/retro` slash commands |
| Claude Code (in-repo) | `npx agentic-discipline init` | `.claude/skills/agentic-*/SKILL.md` |
| Cursor | `npx agentic-discipline init` | `.cursor/rules/agentic-*.mdc`, scoped by `globs` |
| GitHub Copilot | `npx agentic-discipline init` | `.github/instructions/agentic-*.instructions.md`, scoped by `applyTo` |
| Windsurf | `npx agentic-discipline init` | `.windsurf/rules/agentic-*.md`, with trigger modes |
| Antigravity | `npx agentic-discipline init` | `.agents/skills/agentic-*/SKILL.md` |
| Gemini CLI | `npx agentic-discipline init` | `GEMINI.md` |
| Codex, Zed, Cline, Aider, Jules | `npx agentic-discipline init` | `AGENTS.md` |
| ChatGPT (web) | `npx agentic-discipline init --adapter chatgpt` | a paste-ready bundle, see below |

Emit a specific set instead of auto-detection:

```bash
npx agentic-discipline init --adapter claude --adapter cursor
```

List everything the compiler supports:

```bash
npx agentic-discipline adapters list
```

## ChatGPT

ChatGPT has no project filesystem, so it is the one tool where you paste rather
than run a command. `--adapter chatgpt` writes a single bundle to
`.agentic/export/chatgpt/agentic-discipline.md`; paste it into a Project's
instructions or a Custom GPT.

Codex is different: its CLI and cloud agents read `AGENTS.md`, which `init`
already writes, so Codex needs no bundle.

## Keeping the surfaces current

Every surface is compiled from `disciplines/` in this repository. After the kit
updates, or after you edit a discipline, recompile:

```bash
npx agentic-discipline adapters sync
```

The command is idempotent, replaces only the region between its managed
markers in shared files such as `AGENTS.md`, and removes generated files for
disciplines that no longer exist.

Each discipline declares two things: what it does (`description`) and when it
applies (`when_to_use`). Tools that support both fields receive them separately;
tools with a single description field receive them combined, so a rule scoped by
`globs` still tells the model when it is relevant.

## The CLI, for gates and CI

The disciplines above are markdown; the deterministic checks are a program.
Install it when you want `quality`, `verify`, `risk` or `evidence`:

```bash
pipx install agentic-discipline-kit
```

Alternatives: a standalone executable from
[Releases](https://github.com/lreyesm1999/agentic-discipline-kit/releases),
the container image, or the repository's composite action, which installs the
CLI on the runner for you:

```yaml
- uses: lreyesm1999/agentic-discipline-kit@v1
  with:
    config: agentic.config.json
```

From source, for contributors (Python 3.11+):

```bash
python -m pip install -e ".[dev]"
```

## Generated quality gates

`init` reads your project manifests and generates gates for the detected
stacks. A gate whose command cannot run here - a missing executable, or an npm
script your `package.json` does not define - is written with `required: false`
and a `note` explaining why:

```json
{
  "name": "typescript/lint",
  "command": "npm run lint",
  "required": false,
  "note": "disabled by init: package.json defines no 'lint' script"
}
```

Nothing is ever silently enabled. Review the relaxed gates, wire up the missing
scripts, and promote them to `required` deliberately.

```bash
agentic-discipline doctor --check-tools
```

## Upgrading from an earlier layout

Installations before this release copied `skills/`, `policies/`, `schemas/`,
`templates/`, `config/` and `MASTER_PROMPT.md` into the repository root. To move
them under `.agentic/`:

```bash
agentic-discipline migrate --to 3.0
```

Review the report at `artifacts/payload-migration-report.json`, then delete the
legacy copies:

```bash
agentic-discipline migrate --to 3.0 --prune
```
