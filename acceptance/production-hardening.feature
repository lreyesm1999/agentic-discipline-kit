Feature: Production-grade deterministic controls

  # REQ: FR-001 FR-002
  @AC-101
  Scenario: an empty quality configuration cannot pass
    Given a quality configuration with no required gates
    When the quality engine validates the configuration
    Then the result is an explicit error rather than pass

  # REQ: FR-003
  @AC-102
  Scenario: an invalid traceability edge cannot satisfy a requirement
    Given a requirement edge that targets a missing node
    When the requirement graph is checked
    Then the graph fails and the requirement remains orphaned

  # REQ: FR-004
  @AC-103
  Scenario: unsupported acceptance syntax is rejected
    Given an acceptance contract containing unsupported Gherkin syntax
    When the acceptance compiler reads the contract
    Then compilation fails with an actionable error

  # REQ: FR-005
  @AC-104
  Scenario: evidence tampering is detected
    Given a valid evidence ledger hash chain
    When a persisted record is modified
    Then ledger verification reports failure

  # REQ: FR-006 SEC-001
  @AC-105
  Scenario: protected contracts are checked in pull requests
    Given a pull request that changes a protected contract
    When the Agentic Integrity workflow runs
    Then the protected-path gate blocks the pull request

  # REQ: FR-007 FR-008
  @AC-106
  Scenario: an installed distribution bootstraps a valid repository
    Given the wheel is installed in an empty environment
    When a supported project profile is bootstrapped into a Git repository
    Then doctor validates its contracts and quality configuration
