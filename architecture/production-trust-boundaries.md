# Production trust boundaries

## Trusted inputs

Protected specifications, acceptance contracts, policies, schemas, skills, workflows and
`agentic.config.json` are executable or authority-bearing inputs. They require human review and
branch protection.

## Untrusted executor

The coding agent may propose changes and run deterministic tools, but may not redefine protected
contracts to make an implementation pass.

## Fail-closed boundary

Missing configuration, metrics, tools, evidence or traceability are failures or errors. They are
never inferred as successful from an absent result.

## Evidence boundary

The local ledger provides hash chaining and concurrency safety. Its final head hash must be
published by CI in an immutable artifact or attestation to detect truncation or wholesale rewrite.

## Shell execution boundary

Quality gate commands execute directly without invoking a platform shell. JSON argument arrays are
preferred to avoid platform-dependent parsing. Configuration must only be read from the reviewed
repository checkout; external or pull-request-supplied configuration is not trusted without review.
