# Validation — Agentic Discipline 2.1

**Not a release.** 2.1 is the adaptive assurance engine together with the zero-touch
operational bootstrap. What follows is the engine, executed in this working tree, and the
pull-request mutation gate recorded from CI. The bootstrap's own gates are not in these
numbers. Absence of a result is not a pass.

Everything below ran on Windows 11 with CPython 3.12.2, in this working tree. Linux
figures from the same tree are noted where they were taken.

## Gates executed

| Check | Result |
|---|---|
| Full Python suite | PASS: 1,941 passed, 26 skipped. Every skip is a POSIX symlink or permission case that Windows cannot express; the same suite runs them on Linux under WSL with nothing skipped. |
| Coverage gate | PASS: 99.16% lines, 97.96% branches against unchanged 90/85 thresholds. The 2.0 baseline on this tree was 98.94 / 97.41, so the change raises both. |
| Coverage of the new engine | PASS: 0 uncovered lines and 0 partially covered branches across the nine assurance modules, and across every 2.0 line this change added. The three remaining gaps in the touched files are pre-existing 2.0 lines: a `__main__` guard, a transaction rollback guard and `invalidate`'s binding handler. |
| Lint and format | PASS: `ruff check .` and `ruff format --check .` |
| Type checking | PASS: `mypy src`, 49 source files |
| Security SAST | PASS: `bandit -r src scripts -q -lll`, no high-severity findings |
| Package build | PASS: `python -m build` produces a wheel containing all nine assurance modules. The new subpackage needs no packaging change; `setuptools` finds it. |
| Repository check | PASS after refreshing `MANIFEST.json`; `scripts/repo_check.py` reports version consistency, protected workflows and manifest integrity |
| Protected contracts | PASS: no protected path is modified. `specs/`, `acceptance/`, `architecture/`, `policies/`, `schemas/`, `skills/`, `disciplines/`, `AGENTS.md`, `MASTER_PROMPT.md` and `.github/workflows/` are untouched by this change. |
| Diff integrity audit | PASS for this change: `agentic-discipline integrity --base-ref HEAD` reports no removed test, no weakened assertion and no disabled gate. Against `main` it reports one removed test in `tests/test_state_and_gitignore.py`, which comes from the branch commit `ec363c2` that preceded this work, not from it. |
| Assurance integrity | PASS: `agentic assurance integrity` and, through it, `agentic doctor` |
| Own-repository execution (dogfood) | PASS: `evidence/dogfood.json` |
| Scoped mutation campaign | PASS: 98.71% of 2,163 mutants killed; every one of the 28 survivors has a reviewed disposition, none unresolved. `evidence/mutation.json` |
| 1,000-file performance fixture | PASS: all targets met, `evidence/benchmark.json` |
| Platform CI matrix | PASS: GitHub Actions run [35906290627](https://github.com/lreyesm1999/agentic-discipline-kit/actions/runs/35906290627), Linux and Windows, Python 3.11, 3.12 and 3.13. |
| Pull-request mutation gate | PASS: the same run, four shards, 14,837 killed of 14,976. 65 proved equivalent by rule, 74 accepted by reviewed exception, none unresolved. assurance 4,553/4,558; control 10,041/10,168; verifier 209/213; core 34/37. A pull request mutates the files its diff can affect, so modules the diff does not touch are not in these totals. |
| Protected paths on that run | FAIL: `guardrails`. The branch changes `policies/mutation-exceptions.json` and `.github/workflows/ci.yml`. Owner acceptance at merge. |
| Human acceptance | Not given. |

## The twelve acceptance scenarios

Each one is a named test in `tests/control/test_assurance_scenarios.py`, and each drives real
processes and persisted records rather than stubs.

| Scenario | Demonstrated by |
|---|---|
| 1 Basic verification | `test_scenario_1_a_task_compiles_obligations_runs_verifiers_and_completes` |
| 2 Failed obligation blocks completion | `test_scenario_2_a_failing_verifier_blocks_completion` |
| 3 Stale evidence | `test_scenario_3_changing_proven_code_stops_the_obligation_being_verified` |
| 4 Unrelated change keeps a narrow claim current | `test_scenario_4_an_unrelated_edit_leaves_a_narrow_obligation_verified` |
| 5 Assurance expansion | `test_scenario_5_a_diff_touching_an_undeclared_surface_adds_obligations` |
| 6 No silent contraction | four tests: retention, refused weakening, the audited waiver, and a waiver refused over current failure |
| 7 Conflicting evidence | two tests, including one that proves execution order cannot turn a conflict into a pass |
| 8 Deterministic dominance | three tests: selection, resolution, and judgment still used when nothing deterministic is declared |
| 9 Progressive escalation | `test_scenario_9_a_route_that_reaches_no_verdict_escalates_to_a_deeper_one` |
| 10 Human required | two tests: the concrete request, and the verdict going stale when what it judged changes |
| 11 Bounded repair | three tests: focused re-verification, a spent budget, and repair authority stopping at scope and protected paths |
| 12 Completion invariant | `test_scenario_12_...` parametrised over the service, the API, the CLI and MCP |

## Property tests

`tests/control/test_assurance_properties.py`, over generated inputs rather than chosen ones:

- a current failure never leaves an obligation `VERIFIED` (and is `CONFLICTED` exactly when a
  current pass sits beside it);
- `VERIFIED` happens only when every required verifier currently passes;
- staling the only proof, or a run whose inputs moved under it, cannot leave `VERIFIED`;
- judgment evidence never closes a claim a deterministic verifier could reach;
- a resolution is always one of the declared states, and `UNKNOWN` is never resolved;
- merging a recompiled obligation can only ask for the same or more — 200 generated
  combinations of criticality, mandatory, enforced, capabilities and depth, each checked to
  be no contraction of what was stored;
- more observed impact never narrows an obligation;
- every capability a deterministic verifier supplies is reported as deterministic, and an
  unknown verifier kind never gains a capability it did not declare.

## Failure injection

`tests/control/test_assurance_failures.py` and `test_assurance_edges.py` do the damage for
real and then ask what the engine claims:

a deleted evidence artefact; a rewritten one; an unreadable one; one whose exit code no
longer matches its row; a stored result relabelled as `PASS`; a verifier that cannot start;
a verifier that exhausts the runtime budget; a run interrupted mid-flight; a failed database
write during plan compilation; tests edited after they proved something; a later pass beside
a current failure; the declared verifiers moved out from under the proof; an obligation
deleted behind the engine; a forged obligation status; a waiver with no recorded reason;
judgment evidence relabelled deterministic; a completed task that later loses its proof; and
an obligation whose paths cannot be measured.

In every case the engine reports the problem or refuses; in none of them does a claim become
verified. The audit chain stays `PASS` after each.

## Scoped mutation campaign

`mutmut run` covers the whole package against the whole suite. In this environment it
exhausts memory while generating that many mutants, and a scoped configuration deadlocks its
workers — a hazard `v2/VALIDATION.md` already records for this project. So the new core was
put through a purpose-built harness, `scripts/assurance_mutation.py`, which rewrites one
syntax node at a time in the nine assurance modules and runs the assurance test selection
against each rewrite.

The harness carries its own control: the modules rebuilt from their own syntax trees,
unmutated, must still pass the selection, or a rewriting bug would look like a suite that
kills everything.

### Result

| | |
|---|---:|
| Mutants generated over the nine modules | 2,163 |
| Killed | 2,135 |
| Survived | 28 |
| Timed out | 0 |
| Mutation score | 98.71% |
| Survivors accepted by review | 28 (24 equivalent, 4 platform) |
| Stale dispositions | 0 |
| **Unresolved after review** | **0** |
| Gate | **PASS** |

The full campaign ran from scratch over the frozen sources in 76 minutes with six workers,
against all eight assurance test files, and left 37 survivors. Nine of those were real gaps
and were killed with tests; because the sources had not changed, only the positions still
alive were run again (`--resume`, which refuses a report from different sources), and the
kills elsewhere were carried over — a suite that only gains tests can kill more mutants but
revive none. `method`, `previous`, `re_evaluated` and `carried_over_kills` in the report say
exactly that.

Every remaining survivor has a reviewed entry in `evidence/mutation-dispositions.json`,
matched by module, the exact source of its line, family and count, in the manner of
`policies/mutation-exceptions.json`. An entry that stops matching fails the gate. The gate
was checked in both directions: it passes with the reviewed list, fails when one entry is
removed, fails when an invented entry is added, and refuses a report produced from other
sources.

- **24 equivalent**: identifiers hashed from an opaque key (6), rank offsets that preserve
  the order they sort by (5), a search one level past the deepest a verifier may declare (2),
  `>=` against `>` on equal values, `return False` against `return None` in a boolean filter
  (2), `supports_incremental: False` on entries where the default is already `False` (8), and
  a `break` whose `continue` reaches the same exit on the next line.
- **4 platform**: file and directory modes and a symlinked evidence directory, which
  Windows does not enforce. `test_a_human_verdict_artefact_is_private` and
  `test_a_human_verdict_refuses_a_symlinked_evidence_directory` pin them on POSIX, where CI
  runs them.

### How it got there

The first full campaign scored **73.5%**: 584 survivors. Most were not equivalent. They were
specification gaps — whole records whose shape nothing pinned — and three were defects:

- **The completion invariant had no test of its own.** Inverting the filter in
  `mandatory_debt` returned an empty list, which would have let a task complete while holding
  proof debt, and every test still passed, because each one that reached completion also
  failed an earlier 2.0 check. `test_completion_is_refused_for_proof_debt_even_when_every_contract_verifier_passed`
  now isolates it.
- **Every recompile wrote a revision that changed nothing.** The merge added a depth field
  the stored obligation did not have yet, so an identical recompile reported obligations as
  widened and grew the audit chain. The depth is now recorded at creation.
- **A human verdict's `binding` field was never read back.** Losing it would have made 2.0's
  `status()` fail on the next invalidation sweep.

Two further campaigns were lost to mistakes of the process rather than the code, and are
recorded because the second one is the kind of error this engine exists to catch: one was
killed when a session ended, and one ran against a hand-written test list that left out the
newest test file, so it measured an older suite. The harness now writes a journal as it
goes, runs detached, and discovers its test selection with a glob.

CI run 35906290627 is the pull-request scope in the table above, not a fresh pass over
every module. On a pull request each of the four shards mutates only the files that diff
can affect; on `main`, and on a manual run, each shard mutates its whole tree.

## Measured cost

From `evidence/benchmark.json`, on the synthetic 1,000-file fixture with a real verifier
execution. Targets are the limits the script enforces; it exits nonzero if any is missed.

| Operation | Median | Target |
|---|---:|---:|
| Assurance plan compilation | 2.2 ms | 600 ms |
| Assurance reconciliation, including impact | 305.5 ms | 900 ms |
| Obligation resolution for a task | 204.3 ms | 400 ms |
| Staleness recalculation after an edit | 206.9 ms | 400 ms |
| 2.0 status | 253.2 ms | 300 ms |
| 2.0 claim | 164.4 ms | 200 ms |
| 2.0 checkpoint | 155.2 ms | 300 ms |

Three consecutive runs on the final sources met every target, with `claim` at 164 ms each
time. One earlier run measured `claim`, a 2.0 operation sampled once, at 385 ms and failed
it; that run is not the recorded one, and it is mentioned so the recorded one is not read as
the only result. Run-to-run variance on this machine is roughly a factor of two, and the
script exits nonzero whenever a target is missed.

Compilation is cheap; resolution is dominated by fingerprinting each claim's paths and the
protected tree. Skipping the task-wide binding when every record carries its own halved
resolution from 203 ms to 101 ms. Nothing here has been measured beyond a single-task
1,000-file fixture, and `v2.1/LIMITATIONS.md` says so.

## Dogfood

`evidence/dogfood.json`, produced by `scripts/assurance_dogfood.py` against this repository
in 67 seconds. Its `steps` array is the clearest single view of the engine:

```text
compiled from the declared contract         debt=2  {UNRESOLVED: 2}            EXPAND_VERIFICATION
after running the declared verifiers        debt=0  {VERIFIED: 3}              COMPLETE
after editing a file the proof rested on    debt=3  {STALE: 3}                 EXPAND_VERIFICATION
after restoring that file byte for byte     debt=0  {VERIFIED: 3}              COMPLETE
after the diff reached a migration surface  debt=4  {STALE: 3, UNKNOWN: 1}     ESCALATE
after removing the surface again            debt=1  {UNKNOWN: 1, VERIFIED: 3}  ESCALATE
when completion was attempted               debt=1  {UNKNOWN: 1, VERIFIED: 3}  ESCALATE
after the recorded waiver                   debt=0  {VERIFIED: 3, WAIVED: 1}   COMPLETE
```

The three verifier executions are real `pytest` processes over the assurance scenarios, the
failure and edge suites, and the property suite, each with its exit code and hashed artefact.
Completion was refused with `PROOF_DEBT` while the migration claim was open, a second task
produced `CONFLICTED` from one passing and one failing verifier, and the task completed only
after an owner waiver recorded a reason and an authority. The integrity check and the audit
chain both end `PASS`.

## What the dogfood caught

It closed a real defect rather than confirming what was already believed. The capability
registry declared a `unit` verifier as supplying `regression`, and a `regression` verifier as
supplying `data_preservation`. That let a unit suite close a migration-safety claim about
data it never examined — the dogfood run completed a task it should have blocked.
Capabilities are now narrow, and the two policy rules that leaned on the loose ones
(`SEC-AUTHZ` accepting any acceptance suite, `FIN-STABLE` accepting a property test for a
claim about recorded history) were tightened with the reason written next to them.

It also showed that the protected-contract obligation could never fire, because the existing
change check refuses a protected edit inside a task outright. That rule was removed rather
than left as a claim nothing could reach.

## Reproduce

```sh
python -m pip install -e ".[dev]"
ruff check . && ruff format --check .
mypy src
pytest -q --cov=agentic_discipline --cov-report=json:coverage.json
python scripts/coverage_gate.py --report coverage.json --min-line 90 --min-branch 85
bandit -r src scripts -q -lll
python scripts/repo_check.py
python scripts/control_benchmark.py --files 1000 --output docs/v2.1/evidence/benchmark.json
python scripts/assurance_dogfood.py --reset --output docs/v2.1/evidence/dogfood.json
python scripts/assurance_mutation.py --dispositions docs/v2.1/evidence/mutation-dispositions.json --journal mutation.jsonl --output docs/v2.1/evidence/mutation.json
agentic-discipline protected --base-ref origin/main
agentic-discipline integrity --base-ref origin/main
```

The dogfood writes only `.agentic/control/`, which is gitignored, and removes the scratch
directory it used. Both it and the mutation harness exit nonzero if what they demonstrate
stops holding.
