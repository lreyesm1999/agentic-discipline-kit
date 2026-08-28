# Recommended GitHub Repository Rules

For the default branch, enable a GitHub ruleset with:

- require pull requests before merging;
- require at least one approving review;
- dismiss stale approvals when new commits are pushed;
- require conversation resolution;
- require status checks to pass;
- block force pushes;
- block branch deletion;
- require signed commits if your organization already uses them;
- restrict bypass permissions to maintainers.

Recommended required checks:

```text
CI / lint
CI / typecheck
CI / test
CI / package
Security / dependency-review
```

For high-risk production repositories, add your project-specific Agentic Quality gate as required.
