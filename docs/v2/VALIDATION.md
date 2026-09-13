# Validation and release disposition

**Implementation: local preview. RELEASE READY: NO.**

Verification artifacts preserve actual executed outputs, not inferred PASS values.
The suite includes the existing v1 tests and new control-plane integration/regression
cases. The source and artifacts are identified in `evidence/validation.json`.

| Check | Current result |
|---|---|
| Full Python suite | 191 passed in the final local run |
| Coverage gate | PASS: 95.01% lines, 87.06% branches; thresholds remain 90/85 |
| Lint and type checking | PASS |
| Security SAST | PASS: no high-severity Bandit findings |
| Package build | PASS: wheel and source distribution |
| Isolated installed wheel | PASS: legacy init, Git setup, new adoption and composed doctor |
| Own-repository task execution | PASS: actual subprocess ran 52 control tests, checkpoint/evidence/task completion persisted |
| 1,000-file performance fixture | PASS after scoped discovery optimization: status 264.851 ms, claim 167.950 ms; all four targets met |
| Protected-contract diff | PASS against the prerequisite autonomy branch |
| Diff integrity heuristic | FAIL: review required for new coverage-related documentation, counters, HTML and artifact hashes |
| Differential mutation | UNRESOLVED: historical verification-module run killed 899 mutants; 288 survived. See evidence/mutation.json |
| Independent review | Focused final review: no remaining HIGH/CRITICAL in reviewed scope; evidence/independent-review.json |
| Remote platform matrix / release approval | Pending; stable release is not claimed |

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

The existing auditor scans added lines for numeric text near words such as coverage
or mutation. It flags the unmodified supplied plan's illustrative percentages,
new coverage counters, a minified HTML string and an evidence hash under a mutation
skill path. These are not changes to the existing 90/85 thresholds. Retain the findings
for review rather than changing the scanner or obscuring the source. The parent
PR also contains its separately documented exact-count/manifest findings.

## Reproduce

```sh
python -m pip install -e '.[dev]'
make check
ruff format --check .
bandit -r src scripts -q -lll
python -m build
python scripts/control_benchmark.py --files 1000
agentic-discipline protected --base-ref origin/feat/autonomous-project-execution
agentic-discipline integrity --base-ref origin/feat/autonomous-project-execution
```

The original protected architecture, policies and quality gates remain authoritative.
Human acceptance, supported platform CI and mutation disposition must be resolved
before a release can be certified.

The previous performance failure is preserved in evidence/benchmark-before-optimization.json. Filtering scope before filesystem metadata checks and skipping unused Git enumeration brings all fixture targets below their unchanged limits. Independent comparison against the previous implementation passed 46 equivalence checks; raw logs are preserved. The historical mutation run predates final hardening; current-code mutation and full critical scope still require execution and survivor disposition.

Remote checks for commit 0f40dfebc75e3dffbb297b950876de8e18aa2dea: all six Linux/Windows Python 3.11–3.13 test jobs, repository/package/lint/typecheck, Python security and CodeQL passed. Dependency review failed because GitHub reports Dependency Graph unavailable/disabled. Integrity findings remain blocked. Mutation was still running when observed. These results do not certify the subsequent optimization commit.
