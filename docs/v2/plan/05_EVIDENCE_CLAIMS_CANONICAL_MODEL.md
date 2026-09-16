# Evidence → Claims → Canonical Knowledge

## Problem

A repository may simultaneously contain:

- old documentation;
- current code;
- failing tests;
- newer product decisions;
- runtime behavior;
- agent inference.

Blind ingestion converts contradictions into corruption.

## Required pipeline

```text
RAW SOURCE
   ↓
EVIDENCE
   ↓
CLAIM
   ↓
RECONCILIATION
   ↓
CANONICAL KNOWLEDGE
```

## Evidence example

```json
{
  "sourceType": "documentation",
  "sourceRef": "docs/i18n.md",
  "observedAt": "...",
  "contentHash": "...",
  "claimCandidate": "System supports English and Spanish"
}
```

## Claim model

Each claim should contain:

- claim ID;
- normalized statement;
- subject entity;
- predicate;
- object/value;
- provenance;
- confidence;
- authority;
- temporal validity;
- verification status;
- conflicting claim IDs;
- disposition.

## Authority and confidence

They are separate.

Example:

| Claim | Confidence | Authority |
|---|---:|---:|
| agent inference | high | low |
| old docs | medium | low/current |
| current test result | high | high for tested behavior |
| explicit current human decision | high | highest for intent |

## Canonicalization

A claim becomes canonical only when:
- no higher-authority contradiction exists;
- required verification threshold is satisfied;
- reconciliation rules allow promotion;
- provenance is present.

## Never do

- do not turn `INFERRED` into `VERIFIED`;
- do not turn `DECLARED` into `OBSERVED`;
- do not delete conflicting evidence;
- do not silently resolve product contradictions.
