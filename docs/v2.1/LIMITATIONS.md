# What the assurance engine does not claim

This extends, and does not replace, the 2.0 [trust boundary](../v2/LIMITATIONS.md): one
trusted OS user on a local filesystem, approved verifiers run without a shell, no OS
sandbox, no hosted service, no network or cost metering. Everything there still applies.

## The engine proves executions, not truth

An obligation is `VERIFIED` when every verifier its route requires has current passing
evidence from a real process the owner approved. That is a statement about executions and
their measured inputs — not about whether the verifier asks the right question. A
`regression` verifier that runs no assertions will still mark a claim verified. The 2.0
verifier sensitivity contract and the integrity audit remain the tools for that, and this
engine does not replace them.

## The compiler works from paths, not meaning

Policy obligations are raised by the same deterministic path patterns
`agentic-discipline risk` uses. That is a coarse signal in both directions:

- A file named `src/billing/invoice.py` raises the financial claim whether or not the change
  touched a calculation.
- A change to money handling in a file with an unrelated name raises nothing. The task
  contract's own acceptance criteria are the only obligations that do not depend on naming.

The compiler reads paths, not diff content, so a change that adds an authorization check
inside an existing file with no matching name is invisible to it.

## Impact is limited to what the graph actually recorded

`IMPACT` obligations come from links the knowledge graph holds. Discovery resolves Python
declarations and their containment; it does not build a call graph, and for other languages
it records file-level observations only. So:

- A requirement gains an obligation when it is *linked* to a changed file. An unlinked
  dependency is invisible.
- Cross-file, cross-language and runtime reachability remain UNKNOWN, exactly as in 2.0.
- `affected_symbols` names the declarations discovery found inside the changed files. It is
  not a claim that those symbols are the ones that changed behaviour.

## Completion still has a conservative task-wide gate

2.1 resolves each claim against its own narrow binding, which is what makes focused
re-verification possible. Completion additionally keeps 2.0's `completion_proof`, which
requires every contract verifier to hold current proof against the **whole declared scope**.

So an unrelated edit inside the scope leaves a narrowly bound policy claim `VERIFIED` — no
rerun needed for it — while the task-wide gate may still require a fresh full run before the
task can complete. That is deliberate: the narrow binding tells you what to re-run, and the
wide one remains a safety net that was never weakened.

## Resolution cost is dominated by fingerprinting

Compiling a plan is cheap (1.5 ms on the 1,000-file fixture). Resolving one is not: each
obligation fingerprints its own paths and the protected tree. Measured figures are in
[VALIDATION](VALIDATION.md). Two consequences:

- A claim whose `affected_paths` is empty falls back to the whole declared scope and costs
  accordingly.
- The task-wide binding is computed only when some evidence record carries no binding of its
  own, which is why a migrated project's first resolutions cost more than later ones.

Nothing here has been measured beyond a single-task 1,000-file fixture. Large multi-task
repositories need measured caching before the same latency is claimed for them.

## `floor` is depth, not a score

Escalation raises the shallowest verifier class a claim will accept. It does not measure
confidence and does not combine: an obligation at depth 3 is not "more verified" than one at
depth 1, it simply refuses a shallower route than the one that failed to answer it.

## Criticality does not force a depth

`CRITICAL` raises the criticality of a claim and the urgency the decision engine gives it. It
does not force the planner to a level-3 route, because a claim a cheap deterministic
verifier genuinely settles should be settled cheaply. Depth required by risk is expressed by
the compiler adding a falsification obligation for HIGH and CRITICAL work. If your policy
requires more than that, declare a verifier with the capability you want and the engine will
demand it — or waive the claim with a reason on the record.

## A waiver is an escape hatch, and it shows

A waiver closes a claim without proof. It cannot hide current refuting evidence, it needs a
reason and an authority, it is on the audit chain, and it is reported separately from
`VERIFIED` in every view. It is still an escape hatch: a project that waives freely gets
exactly the assurance it waived.

## Human verdicts are as good as the human

A recorded human acceptance is `HUMAN` evidence bound to the artefacts it judged. The engine
can prove that somebody was asked, what they were shown, what they said, and that what they
looked at has not changed since. It cannot prove they looked.

## What is not implemented

- **No reference artefact store.** `reference_comparison` and
  `qualitative_reference_comparison` are registry capabilities a project supplies a command
  for. A comparison works today — `test_a_reference_comparison_is_just_another_verifier_...`
  runs a golden-file check and shows that both the reference and the candidate are hashed
  into the claim's binding, so changing either invalidates the comparison. What is missing is
  management: the engine does not store, version or produce golden files, screenshots or
  baselines, and there is no built-in image or schema differ. The two capabilities are kept
  distinct on purpose, so a reviewer's opinion is never selected for a claim a comparator
  can settle.
- **No adversarial reviewer.** `adversarial` is a verifier kind whose command the project
  supplies. The engine gives it a concrete claim, records its verdict as
  `COUNTEREXAMPLE_FOUND`, `NO_COUNTEREXAMPLE_FOUND` or `INCONCLUSIVE`, and refuses to let
  `NO_COUNTEREXAMPLE_FOUND` alone close a claim a deterministic verifier can reach. It does
  not call a model, and nothing in the core depends on a hosted LLM.
- **No cross-task obligation dependencies.** `dependencies` exists on the obligation record
  and is not yet populated; task-level dependencies are still enforced by 2.0's readiness
  and `proof_current`.
- **No obligation-level budgets.** Runtime, retry, file and line budgets remain per task.
- **No mutation gate over the assurance package in CI.** The scoped campaign is a script
  (`scripts/assurance_mutation.py`) with its own gate: it fails on any survivor without a
  reviewed entry in [the dispositions](evidence/mutation-dispositions.json) and on any entry
  that no longer matches a survivor. Its result is recorded in
  [evidence](evidence/mutation.json). It takes over an hour with six workers, so it is run by
  hand, not by CI; CI still runs the repository-wide `mutmut` gate. Four survivors are
  accepted as platform cases because Windows does not enforce file modes or allow the
  symlink; the tests that kill them run only on POSIX.
- **macOS is still not a supported platform**, and nothing here changes that.
