# Persistence, migration and recovery

## Storage

A project owns `.agentic/control/state.db`, with SQLite WAL, foreign keys, optimistic
record versions, append-only revisions and a hash-linked audit. Evidence output is
stored separately under `.agentic/control/evidence/`, with content hashes in SQLite.
Do not commit this directory or agent session files; `init` adds the rule that keeps it
out of history, and running `init` again on a project adopted before 2.0.0 adds the rule
to the block it already has. Adoption refuses symlinked or
unmanaged control directories and builds new state in a staging directory before an
atomic rename. Existing application files and v1 installation payloads are preserved.

Changesets require a current knowledge version and expected entity versions. All
entities in the changeset commit together or roll back. Historical queries are
revision-aware. Deleted code and retired intent retain their history; rediscovery
does not silently reactivate an inactive identity.

## Backup and legacy migration

```sh
agentic backup /private/project-state.sqlite --json
agentic migrate --input /path/to/v1-requirement-graph.json --dry-run --json
agentic migrate --input /path/to/v1-requirement-graph.json --json
```

Backup creates a new SQLite snapshot; it refuses an existing destination. Back up the
evidence directory as well if current proof must survive recovery. Stop writers while
copying the evidence directory, and retain the snapshot and artifacts together. A DB
snapshot alone preserves history but cannot prove a missing verifier artifact.

Legacy import validates the existing requirement-graph schema, retains original
payloads and IDs in an explicit mapping, and is idempotent by source hash. Imported
assertions are historical and require review; legacy PASS strings do not become new
runtime evidence. Original files are not overwritten. The v1 payload-layout migration
remains `agentic-discipline migrate`; it is a separate command with unchanged meaning.

`agentic rollback CHANGESET-ID --reason TEXT` creates a new knowledge revision. It
refuses to overwrite later entity edits or reactivate retired intent. It does not
rewind code, Git commits or production databases.

For full recovery, stop CLI/MCP/console writers, preserve the current control directory
under a separate name, and restore a matched DB/evidence backup into a fresh control
directory. Do not replace a live WAL database. Run `status`, `doctor`, and `reconcile`,
then reverify affected tasks. Keep the original state until recovery is confirmed.

## Leases and interruptions

Claims are serialized by SQLite transactions. Checkpoints include objective, branch,
commit, knowledge version, workspace fingerprint, failures, hypotheses and the exact
next action. A new worker claims available work and resumes without needing chat history.

A running verifier extends its lease through its remaining runtime budget plus a
30-second recovery margin. Expiry never frees a still-budgeted run for concurrent
execution. Normal or exceptional returns clear the run marker; a crashed runner is
recoverable after the bounded deadline. Expired failed tasks become ready. Retry and
runtime budgets remain accumulated across sessions; exhaustion requires an owner to
review the result and create an explicit replacement contract, not reset a counter.

Reconcile observes external edits, preserves source identities on unambiguous exact
renames, retires removed observations and invalidates affected proof. Status also
checks live proof, so a prior COMPLETED label alone never satisfies a dependency.
After integration, current proof is checked against the primary repository, including
when a historical worktree is retained.
