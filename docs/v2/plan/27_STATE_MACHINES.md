# State Machines

## Task state machine

```text
PLANNED
  ↓
READY
  ↓
CLAIMED
  ↓
RUNNING
  ├──→ BLOCKED
  ├──→ FAILED
  └──→ VERIFYING
          ├──→ FAILED
          └──→ COMPLETED
```

Additional transitions:
- COMPLETED → NEEDS_REVALIDATION
- any pre-completion state → CANCELLED
- any active state → SUPERSEDED where plan changes invalidate work.

## Lease state

```text
ACTIVE
EXPIRED
RELEASED
REVOKED
```

## Knowledge lifecycle

```text
ACTIVE
DEPRECATED
SUPERSEDED
RETIRED
HISTORICAL
INVALID
```

## Evidence state

```text
CURRENT_PASS
CURRENT_FAIL
BLOCKED
UNKNOWN
STALE
HISTORICAL_PASS
```

## ChangeSet state

```text
PROPOSED
VALIDATED
IN_PROGRESS
APPLIED
VERIFIED
ROLLED_BACK
REJECTED
```

## Decision state

```text
OPEN
ASSUMED
DECIDED
REJECTED
SUPERSEDED
REVISIT_REQUIRED
```
