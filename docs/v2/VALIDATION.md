# Validation and release disposition

**Implementation: local preview. RELEASE READY: NO.**

Verification artifacts preserve actual executed outputs, not inferred PASS values.
The suite includes the existing v1 tests and new control-plane integration/regression
cases. The source and artifacts are identified in `evidence/validation.json`.

| Check | Current result |
|---|---|
| Full Python suite | 1194 passed in the integrated local run |
| Coverage gate | PASS: 95.01% lines, 87.06% branches; thresholds remain 90/85 |
| Lint and type checking | PASS |
| Security SAST | PASS: no high-severity Bandit findings |
| Package build | PASS: wheel and source distribution |
| Isolated installed wheel | PASS: legacy init, Git setup, new adoption and composed doctor |
| Own-repository task execution | PASS: actual subprocess ran 55 control tests, checkpoint/evidence/task completion persisted |
| 1,000-file performance fixture | PASS after scoped discovery optimization: status 264.851 ms, claim 167.950 ms; all four targets met |
| Protected-contract diff | FAIL by design: the mutation outcome fix modifies `.github/workflows/ci.yml`, a protected path. Authorized by the code owner (@lreyesm1999) on 2026-09-14; the check is not bypassed |
| Diff integrity audit | PASS: gate configuration and test assertions are checked without treating generated evidence or runtime counters as gate changes |
| Differential mutation | FAIL: latest full CI run (34947709223, 732899d) killed 14,159 of 15,335, with 1,169 survivors and 7 timeouts. The first run is in evidence/mutation.json |
| Independent review | Focused final review: no remaining HIGH/CRITICAL in reviewed scope; evidence/independent-review.json |
| Remote platform matrix / release approval | CI for the integrated commit is pending. Stable release is not claimed. |

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

Later CI full differential mutation runs on this branch, after record-level tests closed survivors, report per-mutant outcomes and enforce the gate: 6036a30 left 2,827 survivors, fcbb405 2,488, 18541ea 2,291, a734a8a 2,287, d1bacf1 2,246 (GitHub run 34933040010) and 732899d 1,169 (GitHub run 34947709223: 15,335 variants, 14,159 killed, 7 timed out). The gate remains failed until every survivor is killed or dispositioned.

A separate local selected-module retest was interrupted with its metadata truncated. No complete local mutation count is inferred from that run; the partial diagnostics are recorded in evidence/mutation.json.

CI mutation reporting has been corrected: mutmut export-cicd-stats writes mutants/mutmut-cicd-stats.json on disk; stdout is only a notice. The new mutation outcome step reads that structured file and fails on survivors, timeouts, skipped/no-test variants, interruption, suspicious or invalid data, while upload-artifact retains the report even on failure. Against the prior full CI counts, the gate exits 1. It does not make the survivor debt disappear.

The mutation outcome wiring touches a protected workflow. `agentic-discipline protected --base-ref origin/feat/autonomous-project-execution` returns 1 and names `.github/workflows/ci.yml`. The code owner for `.github/workflows/` (@lreyesm1999, per `.github/CODEOWNERS`) explicitly authorized this workflow change on 2026-09-14. The `protected` check keeps reporting the path, as it does for every protected change; the checker and protected policies have not been weakened. The code owner separately authorized a second change on 2026-09-14 that uploads per-mutant outcomes (`mutants/**/*.meta`) as the `mutation-outcomes` artifact, so survivors can be triaged by module; it adds an upload only and does not change what the mutation gate enforces.
