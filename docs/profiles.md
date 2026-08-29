# Project Profiles

Profiles teach `agentic-discipline init` how to recognize a project ecosystem and which starter gates
to recommend. They do not limit which technologies the quality engine can execute.

## Descriptor

A profile is a small JSON document:

```json
{
  "id": "rust",
  "label": "Rust",
  "config": "rust-quality.json",
  "detectors": [
    {"pattern": "Cargo.toml", "confidence": 1.0}
  ]
}
```

`config` is resolved relative to the descriptor and points to a regular Agentic Discipline quality
configuration. Detector patterns are matched against files in the repository while dependency and
build-output directories are ignored.

Load a profile without modifying the CLI:

```bash
agentic-discipline init --profile-file ./rust-profile.json
```

Use `--profile rust` as well when detection should be overridden rather than inferred.

## Mixed repositories

Each detected ecosystem contributes its gates. A nested component receives `working_directory` in
the generated configuration, so commands run from that component rather than the repository root.
Working directories must remain inside the initialized repository.

## Generic projects

If no descriptor matches, initialization succeeds with the generic profile and a portable
`git diff --check` gate. Replace or extend that gate with the project's real test, build, lint,
architecture, and security commands.
