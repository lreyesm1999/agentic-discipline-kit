---
id: evidence
name: agentic-evidence
title: Evidence Discipline
description: Normalizes executed statuses, commands, exit codes, artifact hashes and provenance into a release record.
when_to_use: When recording or verifying results for a release decision, or when a PASS is being claimed without execution.
globs: artifacts/**
always: false
phase: release
---

# Evidence Discipline

Normalize executed results, statuses, commands, exit codes, artifact hashes, and provenance. Narrative confidence cannot create a PASS.
