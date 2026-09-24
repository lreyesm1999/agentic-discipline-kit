# Agentic Discipline 2.1 — the Adaptive Assurance Engine

> Every change creates proof obligations. A task is complete only when all required proof
> obligations are resolved by current evidence.

2.0 asks whether a task's verifiers passed. 2.1 asks a different question: **is every
claim this change must keep true currently supported by evidence?** The agent does not
declare success; the state of its obligations decides what it is allowed to claim and
whether the work may advance.

```text
Change / Task
  -> Assurance Compiler      the claims this change must keep true
  -> Proof Planner           the cheapest sufficient evidence route for each claim
  -> Verifier selection      capabilities, not tool names
  -> Evidence                real executions, hashed artefacts
  -> Evidence Resolution     per-claim freshness, conflicts, dominance
  -> Assurance State         VERIFIED FAILED UNKNOWN STALE CONFLICTED BLOCKED HUMAN_REQUIRED WAIVED
  -> Decision                CONTINUE REPAIR EXPAND_VERIFICATION BLOCK ESCALATE HUMAN_REQUIRED COMPLETE
```

Everything in 2.0 still works. The engine is off until a project is migrated on purpose
(`agentic assurance migrate`), and newly adopted projects start with it on.

## A proof obligation

A proof obligation is one concrete claim that must remain true for the change to be
considered correct:

```text
Unauthorized callers cannot reach the operations this change touches.
Financial results for existing data are unchanged by this change.
The published interface stays compatible for existing callers.
The migration preserves the data that already exists.
```

Each one records where it came from, what could prove it, which verifiers were selected,
which paths and symbols it depends on, and what its current state is. A task cannot
complete while any mandatory obligation is `FAILED`, `UNKNOWN`, `BLOCKED`, `CONFLICTED`,
`STALE`, `UNRESOLVED` or `HUMAN_REQUIRED`.

## The five commands

```sh
agentic assurance plan TASK-ID            # what must be proven, and how
agentic assurance verify TASK-ID --session-file /private/worker.json
agentic assurance status [TASK-ID]        # counts, proof debt, decision
agentic assurance explain PO-ID           # one claim, its provenance and its evidence
agentic assurance explain TASK-ID         # why the task can or cannot complete
agentic assurance debt [TASK-ID]          # what is still open, by task and requirement
```

`plan --compile` compiles or reconciles the plan, and the owner-side actions round it out:

```sh
agentic assurance registry                # what each verifier kind can prove
agentic assurance integrity               # the invariants, checked against the records
agentic assurance waive PO-ID --reason "..." --authorization "code owner"
agentic assurance resolve PO-ID --decision "..."       # a human verdict, recorded
agentic assurance migrate [--dry-run]
agentic assurance rollback ASSU-ID --reason "..."
```

Every one of them is `--json`-capable and reaches the same application service as the API
and MCP. `status`, `debt` and `explain` also print a plain reading:

```text
TASK-104 ASSURANCE
  Required obligations 12
  FAILED                 1
  HUMAN_REQUIRED         1
  UNKNOWN                1
  VERIFIED               9
  Proof debt           3
  Decision             BLOCK
```

```text
PO-007
Claim:
  Historical profit calculations remain stable.
Origin:
  changed code affects a financial invariant
Affected by:
  src/profit/calculator.py
Evidence:
  EV-118 PASS CURRENT (regression, DETERMINISTIC)
  EV-124 FAIL CURRENT (property, DETERMINISTIC)
Current state:
  CONFLICTED - current evidence both supports and refutes this claim
```

Asked about a task rather than a claim, `explain` answers the question people actually
have:

```text
TASK-104 cannot complete.
12 mandatory proof obligations.
  FAILED            1
  STALE             1
  VERIFIED         10

FAILED:
  PO-007
  Historical profitability results remain stable.
  Reason: current evidence refutes this claim
  Evidence: EVD-223

STALE:
  PO-011
  The published interface stays compatible for existing callers.
  Reason: the evidence for this claim no longer matches current inputs
  Evidence: EVD-118

Required next actions:
  1. Resolve the failure behind PO-007.
  2. Run the verifier for PO-011 and record evidence.
```

Every line of that comes from persisted records and current evidence, recomputed on the
spot. Nothing in it is a stored verdict, and nothing in it is a confidence score.

## Where obligations come from

The compiler is deterministic and never invents product requirements. Each obligation is
traceable to one of two sources, and the record says which:

| Derivation | Source | Enforced |
|---|---|---|
| `CONTRACT` | one acceptance criterion the task contract already declared, bound to the verifiers that contract assigned to it | always |
| `POLICY` | a repository policy applied to observed paths, using the same deterministic risk signals `agentic-discipline risk` uses | once the actual diff confirms the surface |
| `IMPACT` | a requirement or path the change reaches through recorded links | once the actual diff confirms it |

The policy rules, their claims and the capabilities that can discharge them are in
[`compiler.py`](../../src/agentic_discipline/control/assurance/compiler.py). They cover
authorization, money, migrations, public interfaces, concurrency, security, cryptography,
destructive operations, architecture boundaries and deployment configuration, plus a
falsification claim for HIGH and CRITICAL work and a recorded human acceptance for
CRITICAL work.

Protected contracts have no obligation of their own: the existing change check refuses a
protected edit inside a task outright, which is stronger than a claim to be discharged.

## Two compilations, and why the plan only grows

```text
Phase A, before implementing        Phase B, after the diff exists
  task contract                       the actual changed paths
  declared scope                      the symbols in them
  risk and policy                     what those paths reach
        |                                     |
  INITIAL plan (a forecast)           RECONCILED plan (what is enforced)
```

A forecast obligation is recorded but not enforced until the real change confirms it, so
the upgrade never invents a requirement for a surface no diff ever touched. From then on:

> **Assurance scope may expand automatically. Assurance scope must never contract
> silently.**

A recompile may add obligations, widen their paths, raise their criticality, or deepen the
route they require. It can never drop one, make a mandatory claim optional, lower a
criticality, or leave a claim with no verifier. Anything that would do so is refused,
recorded on the plan as a `refused_contraction`, and written to the audit chain. The only
sanctioned contraction is an owner waiver with a recorded reason and authority — and a
waiver is refused outright while current evidence refutes the claim.

## Choosing the evidence

The planner reasons about **capabilities**, not tools. A task contract keeps supplying the
concrete argv; the registry says what each verifier kind proves, how strong that proof is,
and what it costs.

```text
unit          -> unit                                   DETERMINISTIC  low     L1
acceptance    -> acceptance behavioral                  DETERMINISTIC  medium  L1
contract      -> contract_compatibility schema_compat…  DETERMINISTIC  low     L1
integration   -> behavioral integration                 DETERMINISTIC  medium  L2
regression    -> historical_stability regression        DETERMINISTIC  medium  L2
property      -> falsification invariant property       DETERMINISTIC  medium  L2
security      -> authorization_boundary security        DETERMINISTIC  medium  L2
migration     -> data_preservation migration_safety     DETERMINISTIC  high    L2
mutation      -> falsification test_strength            DETERMINISTIC  high    L3
adversarial   -> falsification_review                   AGENT_JUDGMENT high    L3
human         -> human_judgment                         HUMAN          manual  L4
```

`agentic assurance registry` prints the whole table, including `architecture`, `static`,
`coverage`, `reference`, `reference-review` and anything the project registered itself.

Capabilities are narrow on purpose. A unit suite proves unit behaviour; it does not also
stand for regression, or any project with unit tests would already satisfy a claim about
historical data it never examined. The same reasoning keeps `data_preservation` off the
regression verifier: a suite that compares behaviour has not looked at what survived a
migration. Where your suite does more than its kind implies, say so with
`assurance_register_verifier` rather than leaning on a loose default.

Three rules govern selection:

- **Cheapest sufficient.** One acceptable capability discharges a claim, so the planner
  takes the cheapest declared verifier that supplies one — not the least work, the
  cheapest route that is still enough.
- **Falsification first.** Among equally cheap routes it prefers one that tries to find a
  counterexample: a property test over an integration test, mutation as a falsification of
  "these tests would notice a real mistake" rather than a phase that always runs.
- **Deterministic dominance.** While a declared deterministic verifier can reach a claim,
  a judgment route is not a substitute for it — at selection time and again at resolution
  time, where `AGENT_JUDGMENT` evidence does not close a deterministically reachable claim.

## Progressive assurance

A route starts as shallow as the claim allows and goes deeper only when it fails to
settle the claim:

```text
existing evidence -> focused deterministic -> broader / property -> mutation / adversarial -> human
```

Escalation is triggered by `UNKNOWN` or `BLOCKED` — a route that reached no verdict — never
by a plain failure, which means repair, and never by staleness, which means rerun. When a
route escalates, the deeper verifier **replaces** the one that could not answer; the
superseded verdict stays in the ledger, marked as superseded, and never counts as proof
again. Depth, tracked as the obligation's `floor`, can only rise.

Depth required by risk is expressed by the compiler — HIGH and CRITICAL work gets a
falsification obligation — rather than by forbidding cheap proof for claims a cheap
verifier genuinely settles.

## Freshness, and what does not need re-running

Each obligation binds to what its own claim depends on: the paths that raised it, the
requirement versions behind it, the protected tree, its acceptance text, its selected
verifiers, its claim text and the policy. Evidence carries that binding, recorded before
the run.

- Change a file a claim rests on, and the claim goes `STALE`. Restore that file byte for
  byte and it is `VERIFIED` again: freshness is content, not history.
- Change an unrelated file and a narrowly bound claim stays `VERIFIED`, so only what the
  change actually reached has to be re-run.
- A verdict is checked against its own hashed artefact, so editing the stored row to say
  `PASS` does not restore a claim the run failed.

Conservatively, a claim with no path information of its own binds to the whole declared
scope, and evidence recorded before 2.1 binds to the 2.0 task-wide binding.

## Conflicts and unknowns

Current evidence is read together, not in order of arrival. One fresh `FAIL` beside a
fresh `PASS` is `CONFLICTED` — never `PASS`, whichever ran last. A verifier that could not
reach a verdict is `BLOCKED`, a claim no declared verifier reaches is `UNKNOWN`, and
neither is ever treated as resolved.

## Proof debt

Proof debt is the count of mandatory, confirmed obligations that current evidence does not
close. It is a count of claims, not a confidence score — there is no "92% safe" anywhere in
this engine.

```text
Required obligations: 36
Verified:   31
Failed:      2
Unknown:     1
Blocked:     1
Conflicted:  1
Proof debt:  5
```

`agentic assurance debt` reports it by task, by requirement, by criticality and by the
repository area the claim sits in, and names the evidence that stopped speaking for a claim
— which is the question a change that invalidated something leaves behind.

## What the engine decides

`CONTINUE`, `REPAIR`, `EXPAND_VERIFICATION`, `BLOCK`, `ESCALATE`, `HUMAN_REQUIRED` or
`COMPLETE`, from the obligation states plus risk, protected paths and the task's remaining
authority. A failure inside what the contract still authorizes is `REPAIR`; the same
failure reaching outside the declared scope, into a protected contract, or past the retry
budget is `BLOCK`.

## Human-required claims

When no automated verifier can settle a claim, the engine says so with a concrete request
rather than "can you review this?":

```text
PO-017 requires human resolution.
Claim:      A human explicitly accepted this critical change.
Inspect:    src/profit/calculator.py
Already passed automatically: mutation, unit
Remaining judgment: CRITICAL risk requires a recorded human acceptance of src/profit/calculator.py
Resolve with: agentic assurance resolve PO-017 --decision "<text>"
```

The verdict is recorded as `HUMAN` evidence bound to the same artefacts, so it goes
`STALE` when what it judged changes — a human "looks good" does not outlive the thing it
looked at.

## Worked example

> Change the broker profitability calculation.

```text
Assurance Compiler
  PO-001 the new calculation matches its acceptance criterion      CONTRACT
  PO-002 financial results for existing data are unchanged         POLICY   CRITICAL
  PO-003 the published interface stays compatible                  POLICY   HIGH
  PO-004 the tests detect meaningful implementation errors         POLICY   HIGH

Proof Planner
  PO-001 -> acceptance      PO-003 -> contract
  PO-002 -> regression      PO-004 -> property (cheapest falsifying route)

Result
  3 VERIFIED, 1 FAILED

Task completion
  BLOCKED - proof debt 1
```

## Interfaces and operation

- [Architecture and data model](ARCHITECTURE.md)
- [Migrating a 2.0 project](MIGRATION.md)
- [Threat model for the assurance engine](SECURITY.md)
- [Trust boundary and measured limitations](LIMITATIONS.md)
- [Validation evidence](VALIDATION.md)
- [2.0 control plane](../v2/README.md) and its [interfaces](../v2/INTERFACES.md)
