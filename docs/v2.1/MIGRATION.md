# Migrating a 2.0 project to 2.1

The assurance engine is **off** until you turn it on. A 2.0 project keeps its exact
behaviour — the same commands, the same completion rules, the same evidence — until an
owner runs the migration. A project adopted with 2.1 starts on schema 2 with the engine on.

```sh
agentic --root /path/to/project assurance migrate --dry-run --json   # what it would do
agentic --root /path/to/project backup /private/before-2.1.db        # keep a copy first
agentic --root /path/to/project assurance migrate --json             # do it
```

## What the dry run tells you

```json
{
  "dry_run": true,
  "from_schema": "1",
  "to_schema": "2",
  "tasks": ["TASK-..."],
  "acceptance_criteria": 12,
  "evidence_records": 34,
  "becomes": [
    "each acceptance criterion becomes a mandatory proof obligation",
    "policy obligations from the declared scope are recorded but not enforced until the actual change confirms them",
    "existing evidence keeps its artefacts and gains legacy assurance provenance",
    "completion starts refusing a task that holds mandatory proof debt"
  ],
  "unreconstructible": [
    "which obligation a legacy evidence record was produced for, beyond its acceptance criterion index"
  ]
}
```

It writes nothing and leaves the schema alone.

## The five questions the migration has to answer

**What happens to an existing task?** Nothing to the task itself. Its state, lease,
checkpoints, workspace and history are untouched. It gains an assurance plan compiled from
the contract it already has.

**What happens to existing verifier contracts?** Nothing. The task contract is the source
of the concrete argv, before and after. Each acceptance criterion becomes one `CONTRACT`
obligation bound to exactly the verifiers that contract already assigned to it, so the
claim the engine enforces is the claim the project already wrote.

**What happens to existing evidence?** It keeps its artefacts, hashes, timestamps and
results. It gains `assurance_provenance: "LEGACY"` and an `evidence_class` taken from its
verifier kind where the registry declares one, and `MEASURED` where it does not — never a
`DETERMINISTIC` label the migration cannot justify.

**What becomes a proof obligation?** Every acceptance criterion, as a mandatory, enforced
`CONTRACT` obligation. Policy obligations are compiled from the **declared scope** in phase
A and recorded as forecasts with `enforced: false`, so the upgrade does not retroactively
require proof of a surface the task's actual diff never touched. They become enforced the
first time a reconciliation confirms them.

**What stays historical evidence?** The link between a legacy evidence record and a policy
obligation cannot be reconstructed, because nothing measured it. The migration does not
invent one. A legacy record proves the acceptance criterion it was recorded against, and
nothing more — the resolver matches it by that criterion index, exactly as 2.0 did.

## What changes for you afterwards

`agentic task complete` starts refusing a task that holds mandatory proof debt, with
`PROOF_DEBT` and the obligations that are open. Everything else behaves as before.

A task whose evidence is current and whose acceptance criteria are covered completes
exactly as it did in 2.0 — the acceptance obligations resolve from the evidence that is
already there.

## Rolling back

```sh
agentic --root /path/to/project assurance rollback ASSU-... --reason "..." --json
```

The rollback returns the project to schema 1, which turns the engine off again. Every
record is kept and stays readable for audit: obligations are marked as reverted rather
than deleted, the migration record becomes `ROLLED_BACK` with its reason, and both the
rollback and the original migration are on the audit chain.

Migrating again after a rollback reactivates the same obligations rather than creating
duplicates — obligation identity is derived from the task and the origin, not from when it
was compiled. Obligations compiled *after* the migration are not named by its record and
are left alone by its rollback.

Both directions are idempotent: migrating twice reclassifies no evidence the second time,
and rolling the same migration back twice is refused with `INVALID_MIGRATION`.

## If you would rather not migrate yet

Don't. `agentic assurance <anything>` answers `ASSURANCE_DISABLED` with the command that
enables it, and the rest of the control plane is unaffected. The backup you took before
migrating restores the exact prior state if you would rather go back that way.
