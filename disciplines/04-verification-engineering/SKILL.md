---
id: verification
name: agentic-verification
title: Verification Engineering
description: Reuses or engineers the smallest deterministic verifier for a measurable claim, with declared pass/fail semantics, dependencies, isolation and sensitivity.
when_to_use: When a claim needs proof, when a verifier may already exist, or before trusting a newly generated verifier.
globs: .agentic/verification/**,checks/**
always: false
phase: verification
---

# Verification Engineering

For each important claim, classify mechanizability, discover existing verification, and reuse it before generating a verifier. A generated verifier must declare its requirement, pass/fail semantics, dependencies, isolation, and sensitivity method before it can become trusted.

Use `agentic-discipline verifier register`, `verifier validate`, and `verify` for deterministic execution and evidence.
