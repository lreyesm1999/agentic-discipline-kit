# Architecture

Agentic Discipline Kit separates **reasoning roles** from **measurement roles**.

## Control plane

The control plane is composed of:

- `AGENTS.md`
- `MASTER_PROMPT.md`
- `skills/`
- `policies/`

These files define authority, workflow states, role boundaries, and stop conditions.

## Evidence plane

The evidence plane contains deterministic outputs:

- test reports
- coverage metrics
- CRAP metrics
- mutation reports
- architecture violations
- security findings
- integrity findings
- evidence hashes

An LLM can summarize this evidence, but it must not manufacture it.

## Contract plane

Protected contracts live under:

```text
specs/
acceptance/
architecture/
policies/
```

Production-code agents are intentionally lower-authority than these contracts.

## Traceability plane

The requirement graph creates typed edges between:

```text
Requirement
→ Specification
→ Acceptance
→ Task
→ Test
→ Code
→ Evidence
```

This helps detect dropped requirements and orphaned implementation.

## Review isolation

For high-risk changes, the reviewer should reconstruct intent from the protected contracts before
reading the implementation diff. The implementer's explanatory summary should not be treated as
review evidence.
