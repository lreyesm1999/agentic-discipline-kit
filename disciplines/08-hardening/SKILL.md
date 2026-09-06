---
id: hardening
name: agentic-hardening
title: Hardening Discipline
description: Applies property tests, mutation, security, integrity and negative controls without weakening any gate.
when_to_use: When strengthening a change, when tests are added or modified, and whenever a failing gate tempts a relaxed threshold.
globs: tests/**,**/*_test.*,**/*.test.*,**/*.spec.*
always: false
phase: hardening
---

# Hardening Discipline

Challenge implementation and verification with property tests, mutation, security, integrity, and negative controls. Never weaken a failing gate.
