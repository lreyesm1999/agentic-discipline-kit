# Risk Classification Policy

Risk is estimated from observable change factors, not from agent confidence.

Signals:
- auth/authz impact
- money/ledger/billing impact
- data migration
- public API change
- concurrency
- security-sensitive code
- architecture boundary crossing
- number of files/modules changed
- infrastructure/deployment impact
- cryptography
- destructive operations
- externally visible contract changes

The risk engine proposes LOW/STANDARD/HIGH/CRITICAL.
The human or repository policy may override upward.
Downward overrides should require justification.
