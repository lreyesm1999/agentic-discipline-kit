# Context Engine and Context Audit

## Goal

Give agents the minimum sufficient context to act safely.

## Input

```text
TASK ID
AGENT CAPABILITIES
CONTEXT BUDGET
CURRENT KNOWLEDGE VERSION
```

## Output

```text
TASK CONTRACT
ACTIVE REQUIREMENTS
RELEVANT DECISIONS
RELEVANT ARCHITECTURE
RELEVANT CODE LOCATIONS
RELATED TESTS
CURRENT FAILURES
RECENT DISCOVERIES
CHECKPOINT
EVIDENCE REFERENCES
RISKS
```

## Context layers

### Tier 0 — Mandatory
Never compress:
- task objective;
- acceptance criteria;
- active constraints;
- security restrictions;
- exact failing assertion;
- current checkpoint;
- protected human decisions.

### Tier 1 — High relevance
- directly affected architecture;
- relevant code symbols;
- current tests;
- dependencies.

### Tier 2 — Supporting
- related history;
- old alternatives;
- neighboring modules.

### Tier 3 — Optional
- broad repository background.

## Context audit

Measure:
- instructions;
- discovery metadata;
- project context;
- code snippets;
- logs/tool output;
- handoff state;
- conversation carryover.

Report:
- estimated footprint;
- relevance;
- duplication;
- compression candidates;
- authority class.

## Context-low mode

When context/headroom is low:
1. stop starting new subproblems;
2. stabilize current workspace;
3. run relevant local verification;
4. checkpoint;
5. record current hypothesis;
6. record next action;
7. release or transfer lease.
