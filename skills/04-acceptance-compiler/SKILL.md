# 04 — Acceptance Compiler

## Purpose
Compile acceptance scenarios into a stack-neutral IR and executable adapter outputs.

## Trigger
Acceptance scenarios exist.

## Inputs
- .feature or structured acceptance files
- adapter config

## Outputs
- acceptance.ir.json
- generated executable test skeletons

## Procedure
1. Parse scenario IDs, requirement IDs, steps, and tags.
2. Emit stable stack-neutral JSON IR.
3. Select adapter by configured stack.
4. Generate test skeletons only in generated test paths.
5. Never modify source acceptance files.
6. Fail on ambiguous or malformed acceptance.

## Evidence required
- IR artifact
- compiler output

## Forbidden
- changing acceptance source
- inventing missing behavior

## Stop conditions
- parser ambiguity
- unsupported step without adapter mapping

## Definition of done
- acceptance IR is valid and generation succeeds
