# Quality Gates Policy v2

## Deterministic evidence

A gate must be based on command output or a structured artifact.

Preferred metrics:

```text
line_coverage >= configured
branch_coverage >= configured
max_crap <= configured
architecture_violations == 0
critical_security == 0
high_security == 0
critical_mutation_survivors == 0
mutation_score >= configured
```

## Ratcheting

For legacy code:
- capture baseline;
- forbid regression;
- apply stronger thresholds to changed code;
- ratchet upward over time.

Do not permanently weaken targets simply because a legacy repository fails them today.
