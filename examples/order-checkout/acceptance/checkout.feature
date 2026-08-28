Feature: Checkout total

  # REQ: FR-001 FR-002
  @AC-001
  Scenario: total for positive items
    Given a cart with valid positive item prices
    When the checkout total is calculated
    Then the total equals the sum of the items
