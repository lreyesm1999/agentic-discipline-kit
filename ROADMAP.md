# Roadmap

What is not built yet. Delivered work is in [CHANGELOG.md](CHANGELOG.md); the control
plane's own limits are in [docs/v2/LIMITATIONS.md](docs/v2/LIMITATIONS.md).

## Near term

- native acceptance code generators for TypeScript, Python, and .NET;
- dependency-graph-based affected test selection, rather than the path-based
  `scripts/affected_scope.py`;
- SARIF output for integrity and policy findings;
- macOS as a supported platform, which needs CI to run the suite there first.

## Later

- Go, Java, Rust, and mobile adapters;
- policy packs by risk domain;
- non-Python symbol and call resolution in the control plane's discovery;
- measured caching for repositories much larger than the recorded 1,000-file fixture;
- diff-content signals for the assurance compiler, which today reads paths only;
- obligation-level dependencies and budgets, which are per task today;
- a managed reference-artefact store for the `reference_comparison` capability;
- a CI mutation gate scoped to the assurance package, alongside the repository-wide one.
