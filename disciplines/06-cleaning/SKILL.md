---
id: cleaning
name: agentic-cleaning
title: Cleaning Discipline
description: Removes duplication and temporary artifacts, classifies replacements, and re-verifies after cleanup.
when_to_use: After behavior works and before opening a change for review.
globs: **/*.py,**/*.ts,**/*.tsx,**/*.js,**/*.jsx,**/*.cs,**/*.go,**/*.rs,**/*.java
always: false
phase: implementation
---

# Cleaning Discipline

After behavior works, remove duplication and temporary artifacts, classify replacements, and re-run relevant verification after cleanup.
