---
name: agentic-autonomous-project-execution
description: Executes an authorized software plan across tasks, validating and recording progress until completion or a real blocker requires human input. Use for implementation requests, not analysis-only or planning-only work.
when_to_use: When asked to implement a project, execute a documented backlog, or resume authorized software work with minimal supervision.
---

# Autonomous Project Execution

Executes an authorized software plan across tasks, validating and recording progress until completion or a real blocker requires human input. Use for implementation requests, not analysis-only or planning-only work.

**When to use.** When asked to implement a project, execute a documented backlog, or resume authorized software work with minimal supervision.

Advance all executable work within the user's requested scope. A completed analysis,
plan, file, endpoint, or individual slice is a checkpoint, not a reason to end the
turn while authorized work remains.

**READ → UNDERSTAND → PLAN → IMPLEMENT → VERIFY → FIX → RECORD → CONTINUE**

This discipline coordinates the existing lifecycle; it does not replace acceptance,
risk classification, protected contracts, quality gates, or release requirements.
Apply the relevant disciplines as each slice reaches their phase.

## Establish operational readiness before executing

```text
IF   Agentic Discipline is installed
AND  the user asks for implementation or execution
THEN verify operational readiness first

IF   the control plane is missing
AND  a safe automatic bootstrap is possible
THEN initialise and adopt it automatically

NEVER continue silently without the control plane while claiming
      full Agentic Discipline execution
```

Before the first edit of a real execution, check installation, version, control plane,
repository adoption, project knowledge, Git state, quality configuration and task
orchestration. Where the kit is installed, `agentic preflight` performs those eight checks,
repairs what can be repaired without a decision, and reports one mode:

- **FULL** — the whole workflow is available. Proceed.
- **DEGRADED** — proceed only after stating what is unavailable and why. Never describe
  degraded work as full Agentic Discipline execution, and stop when the task needs what is
  missing.
- **BLOCKED** — do not start. Report the precise reason and what would unblock it.

Repair only what cannot lose data, cannot change business intent, needs nothing outside the
machine and writes only the kit's own files. Never adopt beside an unexplained control
directory, never work around an audit chain that does not verify, and never create a second
state database: each of those needs a person.

## Turn the request into governed work

Do not ask the user to write a task contract, create a task, mark it ready, register an
agent or claim a lease. Where the kit is installed, `agentic work start "<request>"` links
the request to work that already exists or derives the contract from what is recorded: the
request itself, the project's requirements, its knowledge index, its quality gates, its risk
rules and its policy. Verifiers are the project's own gates; nothing is invented to run.

Record the request verbatim as the objective, and keep the derivation traceable. Do not fill
in detail nobody stated. Stop and ask when the decision is the user's: no scope can be
derived, the scope touches a protected contract, the project's rules make the work
`CRITICAL`, or no declared gate proves behaviour. Finish the independent work first, then ask
one precise question.

## Keep the record while the work runs

Take a checkpoint without being asked, at each moment where losing the thread would cost
real work: a completed slice, before a risky operation, before releasing a lease, on a
blocker, at a context limit, before a handoff, before integration. State what was being
attempted and what comes next; the rest - changed files, commands, results, failures - is
read from the records rather than retyped, so a checkpoint never disagrees with the evidence
beside it. A checkpoint with nothing proven says so.

Run the task's verifiers when the work reaches a verifiable state, without waiting to be
told, and record the evidence. Complete only when dependencies are satisfied, the scope held,
contracts were respected, a current checkpoint exists, verification passed on current
evidence and no mandatory proof obligation is outstanding. A failing gate and unresolved
proof debt are refusals, not warnings. Then continue with the next task whose turn it is.

## Establish the execution boundary

1. Read repository instructions and inspect the working tree before editing. Preserve
   user changes, existing valid implementations, and established architecture.
2. Find the relevant specification, acceptance criteria, implementation order, backlog,
   decisions, and current status. Read what the next task depends on; do not load every
   document repeatedly or redesign requirements that are already settled.
3. Compare documented status with code and executed evidence. A checkbox is not proof.
   Identify completed, executable, blocked, and out-of-scope work.
4. Follow the documented dependency order. Prefer a small vertical slice with observable
   behavior across input, processing, persistence, and its API or UI where applicable.
   Use existing scaffolding; create only what the approved behavior needs.

An instruction to execute a plan covers its ordinary implementation and verification
steps. A backlog entry alone does not expand the current request or authorize spending,
production changes, destructive actions, publication, or protected-contract edits.
Honor authorization already given in the session; do not ask for it again. Prepare
all permitted, reviewable work before reaching an action that needs new authorization.

## Execute continuously

Repeat while executable tasks remain within scope:

1. Select the next unblocked slice and its acceptance criteria. Classify its risk using
   the project's rules and identify the commands that can verify it.
2. Implement the behavior. Reuse project components and dependencies before adding
   alternatives. Choose a new dependency only for a clear need and record significant
   architecture or maintenance consequences.
3. Run the relevant verifier. For behavioral changes, establish a failing baseline
   before the fix when feasible. Apply focused tests, integration tests, lint,
   typechecking, build, schema checks, and local migration checks as relevant; run all
   gates required by the project's risk profile before claiming readiness.
4. Diagnose and repair failures caused by the slice, then rerun the affected checks.
   Do not disable tests, lower thresholds, alter protected expectations, or add a fake
   fallback to turn a failure green. If a pre-existing failure is unrelated, record its
   evidence and effect on verification; do not turn it into an unrelated rewrite.
5. Record the slice's actual status and evidence. Continue immediately with the next
   eligible slice, without asking whether to proceed to another phase.

Use verification proportional to the change. Documentation-only work may need link,
format, packaging, and integrity checks rather than invented behavioral tests. Reuse
adequate verifiers. Broaden checks when a required gate or a concrete remaining risk
calls for them, not simply because more tools are available.

Never present mock data, hardcoded users, fabricated statistics, canned success
responses, or TODO paths as finished product behavior. Test fixtures and explicitly
labeled development doubles are valid; an untested external integration remains
unverified even when its contract tests pass.

Give necessary temporary solutions a tracked debt item, limitation, and removal
condition. Follow the cleaning discipline for temporary scripts and artifacts: retain
useful tests and reusable tooling, remove work-owned debris, preserve user files, and
re-verify after cleanup. Record optional ideas as future considerations without
adding them to the current execution queue.

## Decide without unnecessary questions

| Situation | Action |
|---|---|
| Internal names, folders, ordinary UI details, local configuration, routine refactoring or test selection | Follow conventions and decide. |
| Unspecified technical choice with moderate consequences | Prefer the compatible, reversible option; record significant assumptions. |
| Conflicting protected requirements or a choice with substantial business or architectural consequences | Isolate dependent work, describe the conflict, and complete independent tasks first. |
| Missing credential, unavailable required service, denied access, or an action outside current authorization | Prepare adapters, configuration, tests and other independent work; request only the missing input when necessary. |

Do not treat a conventional technical decision as a human blocker. Do not mistake a
deployment credential for a blocker to local implementation. Do not silently choose
pricing, a paid provider, or a destructive production migration merely to keep moving.
Use the host's secure credential flow; never request secrets in committed files or logs.

## Bound failures and isolate blockers

A blocker normally affects a task and its dependents, not the entire project.
Mark that branch blocked and continue unaffected work. For a specification conflict,
use the repository's `SPEC_CONFLICT` protocol; do not implement either interpretation
as though it were approved.

Make repair attempts only when a changed hypothesis, code change, or new evidence can
produce progress. Do not repeat an identical failed command indefinitely. After three
unsuccessful attempts at the same failure without meaningful new evidence, record the
attempts and isolate the task. Respect any stricter project or tool retry limit.
Do not retry denied actions through alternate routes to bypass an access control.

If a repair destabilizes the tree, use a known-good checkpoint only for work you own;
never discard the user's changes or reset a shared branch. An unavailable required
check is `BLOCKED` or `UNKNOWN`, never `PASS`. Other slices may proceed, but the affected
behavior and overall release cannot be declared verified while required gates fail
or lack evidence.

## Keep resumable state

Update the existing project tracker. If there is none, use
`docs/IMPLEMENTATION_STATUS.md`; do not maintain competing status files. At meaningful
checkpoints record:

- **Completed:** requirement/task IDs, implementation locations, and validation evidence.
- **In progress / pending:** current slice, dependencies, and next executable task.
- **Blockers:** affected tasks, observed failure, attempts, and exact missing input.
- **Technical debt / deviations:** temporary limitations and significant differences
  from the approved plan, with their disposition or authorization.

For verification evidence, keep the command, tool, exit code, timestamp, and output
artifact or existing ledger reference. Distinguish not run, failed, blocked, and passed.
Use `docs/DECISIONS.md`, an existing decision log, or an ADR for significant choices:
context, alternatives, decision, reason, consequences. Do not write an ADR for every
internal name or minor edit.

After an interruption or context limit, reread the tracker and working tree, verify
the last checkpoint, and resume the next unblocked task without repeating completed work.

## Communicate and finish

Give brief progress updates at meaningful milestones and at the cadence required by
the host. State what is verified, what remains uncertain, and what you are doing next;
an update is not a permission request. Avoid “Should I continue?” when the next step
already follows from the user's goal.

End the execution only when:

- The requested goal meets its acceptance and required verification criteria.
- All remaining in-scope tasks depend on real human or external blockers.
- The available scope contains no further executable tasks; report any gap between
  the documented plan and the user's goal rather than claiming the goal is complete.
- An objective tool, context, or execution limit prevents more work. Save a resumable
  checkpoint and identify that limitation; never promise unattended background work.

Before asking a blocking question, finish the independent work. State the blocker,
why it matters, what is already verified, the recommended option and material
alternatives, then ask one precise question that would unlock the next step. Do not
ask the user to solve a routine technical failure that available tools can diagnose.

In the final report, prioritize completed behavior, executed checks and their results,
current state, remaining work, blockers, and the next action. Preserve any required
repository report format. Distinguish implementation complete from verified or
released; do not claim overall completion because one stage ended.

## Non-negotiables

1. Human-approved intent and protected contracts outrank convenience.
2. Understand the relevant source, tests, contracts, and commands before changing code.
3. Preserve approved behavior and make the smallest coherent change.
4. Reuse an existing adequate verifier before generating one.
5. If a measurable claim lacks a verifier, engineer the smallest deterministic verifier and prove its sensitivity.
6. Evidence comes from execution; `UNKNOWN` and `BLOCKED` are never `PASS`.
7. Never weaken gates, thresholds, fixtures, or verifier semantics to obtain green.
8. Every replacement, temporary artifact, fallback, test, and verifier needs an explicit lifecycle disposition.
9. Cleanup is followed by re-verification.

## Deterministic checks

Measurable claims are proved by execution, not narration. When the CLI is available:

```bash
agentic-discipline quality --config agentic.config.json
agentic-discipline verify <VERIFIER-ID>
```
