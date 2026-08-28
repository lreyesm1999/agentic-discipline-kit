# Integrity / Anti-Gaming Policy

The following are suspicious when introduced by an implementation agent:

- `test.skip`
- `describe.skip`
- `xit`
- `xdescribe`
- `@Disabled`
- `pytest.skip`
- `pragma: no cover`
- `istanbul ignore`
- `stryker disable`
- blanket `eslint-disable`
- blanket `type: ignore`
- removing assertions
- replacing real checks with tautologies
- hardcoding acceptance outputs
- broad exception swallowing
- disabling CI jobs
- lowering thresholds
- adding exclusions to avoid scanners

Not every occurrence is automatically malicious, but every new occurrence must be reviewed.

Unauthorized quality-gate bypass = blocking failure.
