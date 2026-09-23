# CLI, application API and MCP

`agentic --root PATH api OPERATION --input FILE --json` exposes the versioned service
registry. Inputs are JSON objects checked against `SCHEMAS` in
`src/agentic_discipline/control/api.py`. Unknown fields are rejected. Successful API
results contain `api_version: "2"`, `operation`, and `data`. CLI errors use a stable
`code` and message; operational errors/blocked commands exit 2 and failed verification
exits 1. Human status output and `--json` are views of the same persisted records.

| Area | Operations |
|---|---|
| Observation | `status`, `doctor`, `discover_project`, `reconcile`, `knowledge_health`, `timeline` |
| Knowledge | `query_knowledge`, `knowledge_show`, `knowledge_history`, `impact_analysis`, `record_discovery` |
| Planning | `plan_audit`, `readiness`, `get_ready_tasks`, `task_list`, `get_context` |
| Worker continuity | `agent_join`, `claim_task`, `heartbeat`, `checkpoint_task`, `resume_task`, `release_task` |
| Verification | `record_evidence`, `complete_task`, `integration_gate`, `parallel_safety` |
| Owner authority | `task_create`, `task_ready`, `task_transition`, `resolve_blocker`, `resolve_claim`, `approve_command`, `knowledge_apply`, `knowledge_link`, `lifecycle` |
| Owner workspaces | `workspace_create`, `workspace_refresh`, `workspace_merge`, `workspace_cleanup` |

Owner operations are excluded from the MCP tool list and rejected through its worker
API. Worker discovery submissions are inferred claims; they cannot grant themselves
human authority, set execution state, or promote assertions to verified facts.
For historical queries supply `at_version` to `query_knowledge`; retired entities are
excluded by default and available with `historical: true`.

## Optional Agentic Intelligence handoff

When `.agentic/intelligence/` exists, task readiness reads `readiness.json` and blocks
records whose `id` exactly matches the Agentic Discipline task ID. If
`latest-context.json` has that same `root_id`, mandatory rows in
`executable-constraints.jsonl` are included in the task context. Unapproved mandatory
rows block readiness. The selected constraints and blocker list are hashed into the
verification binding, so a changed handoff invalidates earlier proof. Missing or
malformed handoff files block execution while the handoff directory exists. The two
systems must use the same task ID; this reader does not map IDs automatically or
execute a constraint's `verification` instruction as a command.

## MCP configuration

The server implements the
[MCP 2025-06-18 stdio transport](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)
and [tools interface](https://modelcontextprotocol.io/specification/2025-06-18/server/tools).
It handles initialize, initialized notification, ping, tools/list and tools/call.
Messages are newline-delimited JSON-RPC, limited to 1 MiB; stdout contains protocol
messages only. It does not require an LLM account or host a network MCP endpoint.

Configure the client to launch the installed executable using absolute paths:

```json
{
  "mcpServers": {
    "agentic-discipline": {
      "command": "/absolute/path/to/venv/bin/agentic",
      "args": ["--root", "/absolute/path/to/project", "mcp"]
    }
  }
}
```

On Windows use the installed `Scripts/agentic.exe`. A standalone `agentic` from a
release archive works the same way and needs no Python; so does the npm launcher,
as `npx -p agentic-discipline agentic`. The MCP client receives the
session token from `agent_join` and supplies it to owned task operations. The CLI
instead writes sessions to a new private file outside the repository. Tokens are
hashed in SQLite and omitted from status responses. Treat client transcripts that
contain worker tokens as private.

## Read-first console

Run `agentic console --port 8765`; open `http://127.0.0.1:8765`. Execution, agents and
leases, evidence currency, decisions, requirements, retired intent, discovery coverage
and activity come from current API data. The console has no mutation routes, no CDN
or analytics, a restrictive content policy, and a Host allowlist. It is for the same
local OS user, not remote hosting or multi-tenant access.
