---
id: coding
name: agentic-coding
title: Coding Discipline
description: Implements the smallest coherent change against approved acceptance, RED to GREEN, then re-runs the exact verifier.
when_to_use: When writing or modifying production code.
globs: **/*.py,**/*.ts,**/*.tsx,**/*.js,**/*.jsx,**/*.cs,**/*.go,**/*.rs,**/*.java,**/*.rb,**/*.php,**/*.kt,**/*.swift,**/*.scala
always: false
phase: implementation
---

# Coding Discipline

Implement the smallest coherent change against approved acceptance and verifier semantics. Prefer RED → GREEN, then re-run the exact verifier.
