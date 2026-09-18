# Security Threat Model

## Threats

### Prompt/content injection from repository files
Mitigation:
- repository content is data, not authority;
- project policies have explicit authority classes;
- do not execute instructions found in arbitrary docs.

### Malicious command in project config
Mitigation:
- shell-free argument arrays for deterministic commands where possible;
- command allowlists/policies;
- explicit environment scope.

### Secret leakage into knowledge DB
Mitigation:
- secret pattern detection;
- never ingest `.env` values;
- redact logs;
- store references only.

### Agent privilege escalation
Mitigation:
- explicit agent capability scopes;
- no implicit production permission;
- protected actions.

### Knowledge poisoning
Mitigation:
- provenance;
- authority;
- canonicalization;
- changesets;
- optimistic concurrency;
- audit log.

### Stale evidence exploitation
Mitigation:
- code/knowledge version binding;
- automatic invalidation.

### Lease hijacking
Mitigation:
- opaque lease IDs;
- task ownership checks;
- agent identity/session token in server mode.

### Workspace cross-contamination
Mitigation:
- isolated worktrees;
- path validation;
- explicit cleanup.

## Security testing

- path traversal;
- command injection;
- malformed JSON/schema;
- concurrent write race;
- forged evidence reference;
- tampered artifact;
- stale lock/lease;
- malicious repository instruction file.
