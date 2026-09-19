# Validation and release disposition

**Released as 2.0.0. RELEASE READY: YES** — accepted by the code owner (@lreyesm1999) on 2026-09-19.

Verification artifacts preserve actual executed outputs, not inferred PASS values.
The suite includes the existing v1 tests and new control-plane integration/regression
cases. The source and artifacts are identified in `evidence/validation.json`, and
`evidence/README.md` says which run produced each artifact and which ones a
later run superseded.

| Check | Current result |
|---|---|
| Full Python suite | 1605 passed on Linux in a clean clone of the release branch (evidence/checks.log) |
| Coverage gate | PASS: 98.94% lines, 97.41% branches; thresholds remain 90/85 |
| Lint and type checking | PASS |
| Security SAST | PASS: no high-severity Bandit findings |
| Package build | PASS: wheel and source distribution |
| Isolated installed wheel | PASS: the 2.0.0 wheel in a fresh environment runs `agentic-discipline --version` and `init`, and `agentic --version`, `adopt` and a full-text `knowledge query` (evidence/wheel-smoke.log) |
| Own-repository task execution | PASS: actual subprocess ran 55 control tests, checkpoint/evidence/task completion persisted |
| 1,000-file performance fixture | PASS after scoped discovery optimization: status 264.851 ms, claim 167.950 ms; all four targets met |
| Protected-contract diff | FAIL by design on the release change: it modifies `.github/workflows/release.yml`, a protected path, to build and smoke-test the `agentic` executable. Authorized by the code owner (@lreyesm1999) on 2026-09-19; the check is not bypassed |
| Diff integrity audit | PASS: gate configuration and test assertions are checked without treating generated evidence or runtime counters as gate changes |
| Differential mutation | PASS: CI run 35443136819 (8981c84, merged as b1422cc) killed 15,214 of 15,425 with no timeouts; the gate proves 102 survivors equivalent by rule and accepts 109 through the reviewed exceptions in policies/mutation-exceptions.json, leaving none unresolved. The first run is in evidence/mutation.json |
| Independent review | Focused final review: no remaining HIGH/CRITICAL in reviewed scope; evidence/independent-review.json |
| Remote platform matrix / release approval | PASS: CI run 35443136819 passed the suite on Linux and Windows with Python 3.11, 3.12 and 3.13. macOS is not a supported platform. Release accepted by the code owner on 2026-09-19. |

The benchmark creates an explicitly synthetic source fixture and executes a real
verifier. It is not a production workload claim. `scripts/control_benchmark.py`
reproduces it. The installed-wheel smoke uses a new project and the built wheel,
without importing the editable source checkout.

## Review-driven regressions

Tests cover quoted credential redaction, live/tampered evidence, long dependency
cycles, stale historical proof, expired failed leases, in-flight reruns, independent
parallel integration, active run deadlines, deleted-line budgets, checkpoint hashes,
retained worktrees after primary edits, symlink inputs, canonical human constraints,
post-verification out-of-scope edits, duplicate property symbols, malformed MCP inputs,
nonzero CLI failure exits, composed doctor behavior and interrupted Git/SQLite merges.

## Integrity disposition

The integrity auditor now scopes threshold and workflow checks to gate configuration,
scopes deletion checks to tests and protected configurations, ignores generated evidence,
and recognizes an assertion updated in the same test file. Its checks for weakened
thresholds, disabled workflows, removed tests and removed assertions remain active.
The integrated diff against `main` passes this audit.

## Reproduce

```sh
python -m pip install -e '.[dev]'
make check
ruff format --check .
bandit -r src scripts -q -lll
python -m build
python scripts/control_benchmark.py --files 1000
agentic-discipline protected --base-ref origin/main
agentic-discipline integrity --base-ref origin/main
```

The original protected architecture, policies and quality gates remain authoritative.
Human acceptance, mutation disposition, protected-workflow review and pending CI must be
resolved before a release can be certified.

The previous performance failure is preserved in evidence/benchmark-before-optimization.json. Filtering scope before filesystem metadata checks and skipping unused Git enumeration brings all fixture targets below their unchanged limits. Independent comparison against the previous implementation passed 46 equivalence checks; raw logs are preserved. The historical selected run predates final hardening; the CI full run shows that survivor disposition remains substantial.

Remote checks for commit 0f40dfebc75e3dffbb297b950876de8e18aa2dea: all six Linux/Windows Python 3.11–3.13 test jobs, repository/package/lint/typecheck, Python security and CodeQL passed. These historical results do not certify the subsequent integrated commit.

CI full differential mutation on optimization commit a19c2c196843739507234a93c2581db476b2b0b2 executed 14,934 variants: 9,601 killed, 5,326 survived, 7 timed out (GitHub run 34759274115; process exit 0). The workflow result is green because it does not enforce survivor disposition. This release gate remains failed. Four additional mutation-driven regression tests now pass locally.

Later CI full differential mutation runs on this branch, after record-level tests closed survivors, report per-mutant outcomes and enforce the gate: 6036a30 left 2,827 survivors, fcbb405 2,488, 18541ea 2,291, a734a8a 2,287, d1bacf1 2,246 (GitHub run 34933040010), 732899d 1,169 (GitHub run 34947709223: 15,335 variants, 14,159 killed, 7 timed out), 942c725 833 (GitHub run 34970429525: 15,453 variants, 14,612 killed, 8 timed out), a767274 792 (GitHub run 35038903844: 15,453 variants, 14,653 killed, 8 timed out), 074996d 672 (GitHub run 35058666946: 15,476 variants, 14,796 killed, 8 timed out), a2d5354 669 (GitHub run 35105291913: 15,476 variants, 14,799 killed, 8 timed out) f11b4a7 657 (GitHub run 35146094806: 15,476 variants, 14,812 killed, 7 timed out) and db362f0 692 (GitHub run 35178049230: 15,625 variants, 14,926 killed, 7 timed out). The rise at db362f0 came from code added since, chiefly the retired-test integrity audit and UTF-8 decoding, whose survivors the following commits address. 4705c58 657 (GitHub run 35239651553: 15,584 variants, 14,927 killed, none timed out), 52a7972 649 (GitHub run 35251461126) and 7884b3e 649 (GitHub run 35317358078, same code). Three batches of tests then killed survivors examined one by one: 31e93b2 (#20) left 522 unresolved after the gate's 101, b60a59e (#21) 446, and 80e13ff (#22, GitHub run 35392522637: 15,590 variants, 15,129 killed, none timed out, 125 minutes) 360. The remaining survivors are the equivalents recorded in MUTATION_EXEMPTIONS.md and the corrupt-store guards declared there. The gate remains failed until every survivor is killed or dispositioned. Two intermediate runs (98d9469, 9651d5e) were superseded by later pushes and cancelled before completing, so they report no count.

The a2d5354 mutation job took 309 minutes, against roughly two hours before and a six-hour job limit. A local campaign traced the likely cause to one mutant of the MCP `serve` loop: it stops the loop ending on empty input, so the loop answered with an error forever while the test's output sink copied everything written at each flush. Measured alone it grew memory by 30.9 GB in under ten minutes, which a 16 GB runner can only absorb by swapping until the mutant times out. The sink now refuses to grow past anything a case produces, and the same mutant fails in under a second using 78 MB. The next run, on f11b4a7, took 117 minutes, back to the earlier duration. Its 7 remaining timeouts were each a loop a mutant made endless: file hashing, two graph walks and the `serve` loop. Those loops were rewritten or bounded in their tests, and the 4705c58 run had none, taking 101 minutes.

A local campaign is now a trustworthy fast loop. Run in WSL with the project virtual environment first on `PATH` — mutmut gathers coverage with `pytest -x`, so tests that spawn `python` where only `python3` exists stopped coverage early and silently dropped whole modules from the mutant set — it generates the same 15,476 mutants as CI. Compared mutant by mutant against the 074996d run, it disagreed only where tests added since kill a CI survivor, never reported a CI kill as a survivor, and differed otherwise only by extra timeouts, which count as unresolved rather than as kills.

Survivor triage is recorded in docs/v2/MUTATION_EXEMPTIONS.md: mutants proven to change nothing any caller can observe, each with the argument and the executed check behind it, and separately the survivors that are left unkilled rather than written off. `scripts/mutation_gate.py` does not read that file. It subtracts a survivor only in two ways: a mechanical proof by one of its four rules, or a reviewed exception in policies/mutation-exceptions.json, a protected path, so every change to the list shows in the protected check and needs review. Each exception names the function and the exact line the mutant changes, before and after, with its family and reason, so it survives mutmut renumbering; an exception that no longer matches a survivor fails the gate, so killed or removed mutants cannot stay on the list. Each proof was re-run with bytecode caching disabled, because these mutations are length preserving and a cached `.pyc` silently reports a false survivor.

A separate local selected-module retest was interrupted with its metadata truncated. No complete local mutation count is inferred from that run; the partial diagnostics are recorded in evidence/mutation.json.

CI mutation reporting has been corrected: mutmut export-cicd-stats writes mutants/mutmut-cicd-stats.json on disk; stdout is only a notice. The new mutation outcome step reads that structured file and fails on survivors, timeouts, skipped/no-test variants, interruption, suspicious or invalid data, while upload-artifact retains the report even on failure. Against the prior full CI counts, the gate exits 1. It does not make the survivor debt disappear.

The mutation outcome wiring touches a protected workflow. `agentic-discipline protected --base-ref origin/feat/autonomous-project-execution` returns 1 and names `.github/workflows/ci.yml`. The code owner for `.github/workflows/` (@lreyesm1999, per `.github/CODEOWNERS`) explicitly authorized this workflow change on 2026-09-14. The `protected` check keeps reporting the path, as it does for every protected change; the checker and protected policies have not been weakened. The code owner separately authorized a second change on 2026-09-14 that uploads per-mutant outcomes (`mutants/**/*.meta`) as the `mutation-outcomes` artifact, so survivors can be triaged by module; it adds an upload only and does not change what the mutation gate enforces.
