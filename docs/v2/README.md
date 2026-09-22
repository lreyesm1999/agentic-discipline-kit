# Agentic Discipline 2 — local execution

The `agentic` command adds persistent project knowledge, executable task contracts,
checkpoints, agent leases, isolated Git workspaces and current verification evidence.
CLI, MCP and the project console use the same application services and SQLite state.
The existing `agentic-discipline` commands, adapters and release gates remain available.

Released as 2.0.0 in the Python distribution, the standalone executables and the npm
launcher (`npx -p agentic-discipline agentic`). It is stable within the trust boundary
in [LIMITATIONS.md](LIMITATIONS.md): one trusted OS user on a local filesystem.
See [implementation status](../IMPLEMENTATION_STATUS.md), [design decisions](AUDIT.md),
and [validation evidence](VALIDATION.md). The supplied [plan](plan/00_README.md) is
preserved as the design input, separately from measured implementation status.

## Install and inspect

Use Python 3.11 or newer, Git, and a Python SQLite build with FTS5 support:

```sh
python -m pip install -e '.[dev]'
agentic adopt /path/to/project --dry-run --json
agentic adopt /path/to/project --json
agentic --root /path/to/project status
agentic --root /path/to/project knowledge query authentication --graph code --json
agentic --root /path/to/project discovery status --json
```

Adoption inspects existing files and creates only `.agentic/control/`. It does not
execute repository instructions, rewrite code, install adapters, or silently claim
runtime understanding. Repeat adoption is idempotent. Binary, oversized and excluded
files are distinguished from inspected text; Python symbols have source locations.
Static coverage is not a runtime correctness score.

`agentic doctor` combines control-state audit with the existing installation doctor.
A repository adopted for observation can still fail doctor until its Git worktree,
contracts, installed disciplines and quality configuration are valid. Use the existing
[install guide](../install.md) for that setup. Do not overwrite existing instructions
merely to make doctor pass.

## Preflight

Every real execution starts here, and so does every agent working in this repository:

```sh
agentic preflight              # checks, repairs what is safe, reports the mode
agentic preflight --no-repair   # report only
```

Eight requirements are reported in order: installation, version, control plane, adoption,
knowledge, git, quality configuration, task orchestration. Whatever can be repaired without a
decision is repaired first, and named in the report. The result is one of three modes:

| Mode | Meaning |
|---|---|
| `FULL` | every requirement is met; the whole workflow is available |
| `DEGRADED` | work can proceed, and the report lists exactly what is unavailable and why |
| `BLOCKED` | the work stops, with the precise reason |

`DEGRADED` exists so that nothing is ever implied. A rules-only project gets the disciplines
and no orchestration, and the report says which five things are gone: task contracts and their
readiness, leases, checkpoints and resumable state, recorded evidence and proof obligations,
and the completion invariant. A project outside git keeps the workflow but loses workspace
isolation, change integrity checks and rollback to a checkpoint.

An operation that cannot honestly run in a mode refuses rather than pretending: `DEGRADED_MODE`
when the work needs orchestration, `NOT_READY` when it needs git or when the mode is blocked.

The same preflight is on the versioned API as the owner-only `preflight` operation. The command
line is what serves a project that has no control plane yet, because opening one requires it to
exist.

## Execute a task

Start with [task.json](../../examples/control/task.json) and replace its objective,
acceptance, paths, requirement IDs, verifiers and budgets for the real project.
Requirements can be registered through `knowledge_apply`; use their returned stable
IDs. An empty requirement list is suitable for the small maintenance example, not
proof of product traceability. Put working input/session files outside the task's
repository so they do not become undeclared source changes.

```sh
agentic plan audit --input /path/to/task.json --json
agentic task create --input /path/to/task.json --json
agentic api approve_command --input /path/to/command.json --json
agentic task ready TASK-ID --json
agentic agent join --name worker-a --session-file /private/worker-a.json --json
agentic task claim TASK-ID --session-file /private/worker-a.json --json
agentic task context TASK-ID --budget 32000 --json
```

`command.json` is an object with `command` equal to the exact verifier argv array in
the contract. Approval is an owner operation, not an MCP worker permission. It must
follow existing project/session authorization; the tool does not require asking the
human again when that authorization already exists.

Implement the task, then save a truthful checkpoint using the
[checkpoint example](../../examples/control/checkpoint.json):

```sh
agentic task checkpoint TASK-ID --input /path/to/checkpoint.json --session-file /private/worker-a.json --json
agentic task verify TASK-ID --session-file /private/worker-a.json --json
agentic task complete TASK-ID --session-file /private/worker-a.json --json
agentic task ready --json
```

Continue with the next ready task. A verification command actually runs the approved
process; callers cannot submit a claimed PASS. Failure exits nonzero. Completion
requires current successful evidence, a valid checkpoint, satisfied dependencies and
scope/protection/budget checks. Completion of a task is not permission to publish or
release a product.

For low context or an external blocker, checkpoint and release the lease. `task block`
accepts `--reason`; the owner records a decision with `api resolve_blocker`, then marks
the task ready. A different agent can join, claim and `task resume` using the durable
checkpoint. Terminal cancellation/supersession is available through `task_transition`.

## Parallel work and integration

Create a workspace with `api workspace_create` and `{ "task_id": "TASK-ID" }` before
claiming. It creates a managed Git worktree and branch from a committed primary tree.
Concurrent leases require separate workspaces, disjoint scopes and boundaries, and
LOW/STANDARD risk. Higher-risk or semantically shared work is serialized.

Commit verified changes in the task worktree. `api integration_gate` checks the current
baseline and proof. The owner uses `api workspace_merge` with the task ID and a session
file for an explicit fast-forward merge. Only then can the task complete. If another
task advanced the primary branch, `api workspace_refresh` rebases committed work;
conflicts abort cleanly and leave the original task commit intact. Reverify afterward.
A failed SQLite update after a successful merge can recover only the exact gated tree.
`workspace_cleanup` removes a clean terminal worktree without deleting its branch.

## Interfaces and operation

- [CLI/API and MCP](INTERFACES.md)
- [Persistence, migration and recovery](OPERATIONS.md)
- [Trust boundary and measured limitations](LIMITATIONS.md)

For a coding agent, the project prompt can stay short:

> Lee la especificación. Usa `agentic-autonomous-project-execution`, consulta el estado
> del proyecto y ejecuta las tareas en el orden documentado. Verifica y registra los
> resultados; continúa hasta completar el alcance o agotar el trabajo no bloqueado.
