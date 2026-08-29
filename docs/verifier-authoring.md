# Verifier authoring

Keep generated verifiers small and requirement-derived. A package contains:

```text
my-check/
├── verifier.json
├── run.py
└── sensitivity.json
```

The metadata must declare `requirement_ids`, a human-readable `claim`, `command`, `timeout_seconds`,
`expected_exit_code`, dependencies, isolation, and a sensitivity method. Use `working_directory: "."`
for a self-contained package; use a project-relative directory when the verifier intentionally runs
from the application root.

New verifiers are `DRAFT`. Include evidence showing that a controlled bad fixture fails, set
`sensitivity.status` to `PROVEN`, then protect the verifier when it is a durable release gate.
Protected metadata changes are rejected until explicitly re-registered and reviewed.
