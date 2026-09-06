---
id: architecture
name: agentic-architecture
title: Architecture Discipline
description: Protects dependency direction, module boundaries and structural invariants, preferring existing analyzers over new ones.
when_to_use: When a change touches module boundaries, dependency direction, package manifests or structural invariants.
globs: architecture/**,**/*.csproj,**/pyproject.toml,**/package.json
always: false
phase: hardening
---

# Architecture Discipline

Protect dependency direction, module boundaries, and structural invariants. Use existing analyzers before creating a project-specific architecture verifier.
