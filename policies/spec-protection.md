# Specification Protection

Protected:

```text
specs/
acceptance/
architecture/
policies/
```

Implementation agents cannot write these paths.

If a protected artifact is wrong:
1. emit SPEC_CONFLICT;
2. identify the minimum conflicting contract;
3. propose options;
4. wait for explicit authorization;
5. make the contract change in a dedicated contract-change step;
6. regenerate acceptance artifacts as needed;
7. re-establish RED before resuming implementation.
