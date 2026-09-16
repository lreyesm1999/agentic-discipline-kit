# Product Vision and Non-Negotiables

## Product definition

Agentic Discipline 2.0 is not a prompt pack and not merely a skill bundle.

It is an **engineering control plane for AI-assisted and AI-autonomous software development**.

It should sit between:

```text
Human / Product Intent
        ↓
Agentic Discipline 2.0
        ↓
Cursor / Claude / Codex / ChatGPT / Gemini / Other Agents
        ↓
Repository / Tests / Build / CI / Runtime
```

Its job is to preserve intent, maintain state, coordinate work, measure proof, and keep project knowledge synchronized with reality.

## Non-negotiable principles

### 1. Evidence outranks confidence
No measurable claim may be accepted from model narration when a deterministic check can establish it.

### 2. Source authority remains explicit
A navigation graph may guide the agent, but the decisive source file remains authoritative for implementation structure. Runtime/tests can be more authoritative for observed behavior.

### 3. Historical knowledge is not active knowledge
Preserve history, but do not inject retired requirements into current execution context.

### 4. Human decisions remain human
The agent may infer, prototype, test, investigate, and choose reversible defaults. It must not silently take ownership of consequential product, security, legal, financial, production, or irreversible decisions.

### 5. Sessions are disposable
No critical state may exist only in chat history.

### 6. Multi-agent coordination is indirect
Agents do not need to talk directly to each other. They coordinate through shared state, task contracts, leases, checkpoints, evidence, and integration gates.

### 7. Local-first
The project must provide useful value on one developer machine and one repository before team/cloud mode exists.

### 8. Minimal sufficient context
Do not maximize context. Deliver only the smallest context package that allows safe execution.

### 9. No silent loss
Any source information dropped during normalization must receive an explicit disposition.

### 10. No silent resurrection
Retired or deprecated requirements must not become active merely because old files still mention them.

## Anti-goals

Agentic Discipline 2.0 is not:

- an IDE;
- a replacement for Git;
- a generic chat history manager;
- a full CI platform;
- a cloud-only agent hosting service;
- a universal source-of-truth database for all company information;
- an excuse to over-engineer tiny repositories;
- a system that copies external projects.

## External inspiration policy

Ideas may be studied from external projects, including SkillMesh and others.

For each researched project, record:

- source;
- revision;
- concept studied;
- accepted idea;
- rejected idea;
- resulting first-party design;
- explicit statement that no third-party code was imported unless separately authorized and license-reviewed.
