# Agentic Discipline Kit

**Evidence-backed engineering controls for AI coding agents.**

Agentic Discipline Kit is a stack-agnostic framework for building software with AI agents without
turning correctness, architecture, security, or testing into matters of model opinion.

The kit combines protected specifications, executable acceptance behavior, deterministic quality
gates, change-risk classification, differential mutation testing, anti-gaming checks, independent
review, traceability, and release evidence.

> **Principle:** if a deterministic tool can measure it, the agent must use the tool instead of
> claiming that the code "looks correct."

## Why this exists

AI coding agents are fast, but speed creates a new engineering problem: an agent can produce a large
amount of plausible code while silently dropping requirements, weakening tests, bypassing tooling,
or changing architecture.

Agentic Discipline Kit moves control to a higher level:

```text
Human intent
   ↓
Requirement graph
   ↓
Specification
   ↓
Acceptance contract
   ↓
Implementation
   ↓
Deterministic verification
   ↓
Independent review
   ↓
Evidence-backed release
```

## Highlights

- **20 focused skills** with explicit inputs, outputs, evidence, forbidden actions, and stop conditions.
- **Protected contracts**: implementation agents cannot silently modify specs, acceptance contracts,
  architecture rules, or policies.
- **Requirement graph**: Requirement → Spec → Acceptance → Task → Test → Code → Evidence.
- **Acceptance IR**: stack-neutral representation for executable acceptance adapters.
- **Risk-aware verification**: LOW / STANDARD / HIGH / CRITICAL.
- **CRAP analysis**: combines complexity and coverage.
- **Property testing** for invariant-heavy logic.
- **Differential mutation testing** for changed critical code.
- **Integrity audit** to detect skipped tests, disabled coverage, ignored linting, and similar bypasses.
- **Metric-aware quality engine** with real thresholds instead of exit-code-only claims.
- **Independent reviewer protocol** designed to reduce anchoring on the implementation agent.
- **Evidence ledger** with SHA-256 hashes.
- **Agent retrospective memory** for recurring workflow failures.

## Installation

Requires Python 3.11+ for the included deterministic tooling.

```bash
git clone <your-repository-url>
cd agentic-discipline-kit
python -m pip install -e ".[dev]"
```

Validate the repository:

```bash
make check
```

or:

```bash
agentic-discipline doctor
```

## Use it in another project

Bootstrap a target project from either a clone or an installed wheel:

```bash
agentic-discipline bootstrap \
  --target ../my-project \
  --stack typescript
```

Supported bootstrap profiles are `typescript`, `python`, and `dotnet`.

The bootstrap copies the agent contracts and templates into the target repository and creates
`agentic.config.json` without overwriting existing files by default.

Install the deterministic CLI from this repository when you want to run the included tooling:

```bash
python -m pip install -e /path/to/agentic-discipline-kit
```

Then start the coding agent with the target project's `MASTER_PROMPT.md`.

## Default lifecycle

```text
/spec <request>
/plan <feature-id>
/risk <feature-id>
/build <feature-id>
/test <feature-id>
/harden <feature-id>
/review <feature-id>
/verify <feature-id>
/release <feature-id>
/retro <feature-id>
```

See [docs/workflow.md](docs/workflow.md) for the full lifecycle.

## CLI

```bash
agentic-discipline doctor

agentic-discipline crap \
  --complexity 7 \
  --coverage 92 \
  --max 8

agentic-discipline compile-acceptance \
  --input acceptance/checkout.feature \
  --output artifacts/acceptance/checkout.ir.json

agentic-discipline graph-check \
  --graph artifacts/requirements/checkout.graph.json \
  --complete

agentic-discipline risk --base-ref origin/main
agentic-discipline integrity --base-ref origin/main
agentic-discipline protected --base-ref origin/main

agentic-discipline quality \
  --config agentic.config.json

agentic-discipline evidence \
  --artifact artifacts/quality-report.json \
  --tool pytest \
  --executed-command "pytest --cov" \
  --exit-code 0

agentic-discipline evidence-verify \
  --ledger artifacts/evidence-ledger.jsonl \
  --check-artifacts
```

## Recommended starting thresholds

| Signal | Suggested default |
|---|---:|
| Line coverage | ≥ 90% |
| Branch coverage | ≥ 85% |
| CRAP for changed functions | ≤ 8 |
| Mutation score | ≥ 80% |
| Critical mutation survivors | 0 |
| Architecture violations | 0 |
| Critical security findings | 0 |
| High security findings | 0 |

For legacy systems, use **ratcheting**: record the current baseline, prevent regression, require
stronger quality on changed code, and improve gradually.

## Repository structure

```text
.
├── .github/                 GitHub automation and contribution templates
├── adapters/                Acceptance adapters by stack
├── config/                  Example quality/risk configurations
├── docs/                    Architecture, workflow, security, adoption
├── policies/                Engineering policies enforced by agents
├── schemas/                 Requirement graph and Acceptance IR schemas
├── scripts/                 Portable command wrappers/helpers
├── skills/                  20 agent skills
├── src/agentic_discipline/  Deterministic Python tooling
├── templates/               Specs, acceptance and release templates
├── tests/                   Tests for the framework itself
├── AGENTS.md                Orchestrator contract
└── MASTER_PROMPT.md         Bootstrap prompt
```

## Supported stacks

The orchestration model is stack-agnostic. Example deterministic tooling is provided for:

- TypeScript / JavaScript
- Python
- .NET

The same model can be adapted to Java, Go, Rust, JVM, mobile, and other ecosystems.

## Security

Do not report vulnerabilities in public Issues. Follow [SECURITY.md](SECURITY.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Pull requests must include evidence for behavior and quality
claims.

## Project status

**v2.1.0 — Production/Stable.** The deterministic core fails closed, validates its contracts,
ships the bootstrap assets in the wheel, and is verified on supported Python versions and operating
systems. Native stack adapters and structured metric parsers will continue to grow.

## License

MIT License. See [LICENSE](LICENSE).
