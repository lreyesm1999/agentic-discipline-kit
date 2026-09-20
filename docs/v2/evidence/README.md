# Evidence

Each file is the preserved output of a command that was actually run. Nothing here is
inferred, and nothing is edited after the run it records. `validation.json` names the
revision the release was judged on, hashes every artifact it cites and every source
file, and records the CI run whose mutation gate passed.

## Current release (2.0.0)

| Artifact | What produced it |
|---|---|
| `validation.json` | The release disposition itself: revision, coverage, checks, source hashes, CI and mutation runs |
| `checks.log` | `ruff`, `mypy`, the suite with coverage, the coverage gate, `repo_check`, `doctor` and `integrity`, run on Linux in a clean clone |
| `build.log` | `python -m build` |
| `wheel-smoke.log` | The 2.0.0 wheel installed in a fresh environment, running both commands |

## Earlier runs, kept as history

These record how the control plane reached the release. They are not re-run, and the
state they describe has moved on; `validation.json` and the table in `../VALIDATION.md`
hold the current results.

| Artifact | What it recorded | Superseded by |
|---|---|---|
| `mutation.json` | The first full CI mutation campaign, with its survivors | The mutation run cited in `validation.json` |
| `mutation-gate-review.json` | The review of the CI gate that fails on unresolved survivors | `policies/mutation-exceptions.json` and the gate's own tests |
| `benchmark.json`, `benchmark-before-optimization.json` | The 1,000-file fixture before and after the discovery optimization | Reproduce with `scripts/control_benchmark.py` |
| `dogfood.json` | The control plane executing a task in this repository | — |
| `independent-review.json` | The focused independent review that closed | — |
| `integrity.log`, `protected.log`, `protected-workflow-review.json` | Integrity and protected-path checks on the branch that changed the CI gate | The same checks in `checks.log` and on every pull request |
| `performance-review-equivalence.log`, `performance-review-tests.log` | The review of the discovery optimization: unchanged results and its tests | — |
| `wheel-smoke.json` | The installed-wheel check before the control plane shipped in every distribution | `wheel-smoke.log` |
