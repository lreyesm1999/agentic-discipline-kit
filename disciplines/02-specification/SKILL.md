---
id: specification
name: agentic-specification
title: Specification Discipline
description: Turns a request into observable behavior with invariants, exclusions and acceptance criteria.
when_to_use: When a request is still expressed as intent rather than behavior, or when material ambiguity would otherwise be resolved silently.
globs: specs/**,docs/**,*.md
always: false
phase: specification
---

# Specification Discipline

Turn a request into observable behavior, invariants, exclusions, and acceptance criteria.

Do not silently resolve material ambiguity; surface it before implementation.
