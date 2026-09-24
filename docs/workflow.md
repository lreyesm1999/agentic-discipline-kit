# Engineering Workflow

## Before any real execution

A request for implementation starts with operational readiness, not with the first edit.
`agentic preflight` checks installation, version, control plane, adoption, knowledge, Git,
quality configuration and task orchestration, repairs what it safely can, and reports
`FULL`, `DEGRADED` or `BLOCKED`. `agentic work start "<request>"` then derives or links the
task, evaluates readiness and claims it; checkpoints, verification and completion follow on
their own while the work runs. The user asks for the work and never runs these by hand.

A degraded mode is always stated: what is unavailable and why, and whether proceeding is
safe. Work that needs the full workflow stops rather than continuing on the rules alone.

## Autonomous execution across phases

For a request to execute or resume an approved plan, apply
`agentic-autonomous-project-execution`. The Claude Code plugin exposes it through
`/agentic-discipline:execute <plan path or scope>`; other adapters expose the same
canonical instructions in their native format.

Repeat the lifecycle below for the next eligible slice until the requested scope
is complete or every remaining task is blocked. Reuse the existing project tracker
or create `docs/IMPLEMENTATION_STATUS.md`, recording task dependencies, actual
verification evidence, blockers, significant decisions, and the next executable task.

A finished phase is not a request for permission to continue. Isolate blocked work
and complete independent tasks before asking a precise human question. Missing
credentials or a failed external check cannot become fabricated success. Respect
the documented risk gates and protected contracts throughout; the execution loop
does not add authority to change them or perform unauthorized external actions.

Analysis-only and planning-only requests do not enter this implementation loop.

## 1. Intake

Capture the original human request without silently simplifying it. Normalize into stable IDs such as
`FR-001`, `NFR-001`, `SEC-001`, and `ARCH-001`.

## 2. Specification

Write implementation-independent behavior, invariants, failures, authorization rules, and migration
expectations.

## 3. Acceptance

Turn MUST behavior into observable scenarios. New behavior should be demonstrated RED before
implementation when practical.

## 4. Acceptance compilation

Compile acceptance scenarios into a stack-neutral IR. Generated test adapters are disposable;
the protected acceptance contract remains the source of truth.

## 5. Plan and risk

Plan vertical slices and classify the change. Verification depth increases with money, auth,
migration, public API, concurrency, security, architecture, or destructive impact.

## 6. Implement

Implement the smallest coherent slice. A coder may not change protected contracts to make the
implementation pass.

## 7. Test and refactor

Use unit/integration tests, property tests when meaningful, and behavior-preserving refactoring.

## 8. Harden

Run CRAP analysis, configured quality gates, differential mutation, architecture, security, and
integrity checks.

## 9. Independent review

For HIGH/CRITICAL work, review from clean context using contracts, diff, architecture, and evidence.

## 10. QA

Validate behavior through the closest real boundary: API, UI, CLI, message bus, or other external
interface.

## 11. Release

Hash evidence and produce an explicit release decision. UNKNOWN is not PASS.

## Assurance: what the change has to keep true

When a project runs the `agentic` control plane with the assurance engine enabled, the
lifecycle above gains one question that governs whether it may finish: **is every claim
this change must keep true currently supported by evidence?**

```text
plan   -> agentic assurance plan TASK-ID --compile     what will have to be proven
build  -> implement the slice
test   -> agentic assurance verify TASK-ID             run only what is open, then resolve
verify -> agentic assurance status TASK-ID             counts, proof debt, decision
```

The obligations come from the task's own acceptance criteria and from repository policy
applied to the paths the change actually touched. A diff that reaches further than the
contract declared adds obligations; nothing removes one without an owner waiver that
records a reason and an authority.

`agentic task complete` refuses a task that still holds mandatory proof debt, so a phase is
finished when its claims are resolved, not when the agent says so. Read one claim with
`agentic assurance explain PO-ID`: what it asserts, where it came from, which paths it
depends on, which evidence currently speaks for it, and what to do next.

Two rules matter more than the commands:

- An agent may discover that **more** assurance is needed. It may never decide that less is.
- `UNKNOWN` is not `PASS`, a stale result proves nothing, and one current failure beside one
  current pass is a conflict rather than a pass.

See [Agentic Discipline 2.1](v2.1/README.md).

## 12. Retrospective

Record agent/process failures separately from product truth. Promote recurring lessons into policy
only through explicit review.
