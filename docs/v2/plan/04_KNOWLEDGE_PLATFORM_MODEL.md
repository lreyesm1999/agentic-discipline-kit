# Knowledge Platform Model

## Why multiple specialized graphs

One universal graph creates ambiguous semantics.

Instead, preserve different questions:

### Requirement Graph
Why does this work exist?

```text
BusinessGoal → Feature → Requirement → AcceptanceCriterion → Task
```

### Architecture Graph
How is the system conceptually organized?

```text
Subsystem → Module → Component → Contract → Dependency
```

### Code Graph
Where does implementation live and how does it connect?

```text
File → Symbol → Calls → Imports → Route → Handler
```

### Decision Graph
Why was a decision made?

```text
Decision → Alternative → Assumption → Constraint → Consequence
```

### Execution Graph
What work can run now?

```text
Task → depends_on → Task
Task → blocked_by → Decision
Task → claimed_by → Agent
```

### Evidence Graph
What proves a claim?

```text
Requirement → Test → TestExecution → EvidenceArtifact
```

### Evolution Graph
What changed over time?

```text
EntityVersion → supersedes → EntityVersion
Artifact → disposition → LifecycleRecord
```

## Cross-graph links

Examples:

```text
Requirement --implemented_by--> CodeSymbol
Requirement --verified_by--> Test
Task --changes--> File
Decision --affects--> Requirement
Discovery --invalidates--> Assumption
ChangeSet --touches--> ArchitectureNode
```

## Stable identity rules

- IDs are immutable.
- Names may change.
- Paths may change.
- Git renames do not change semantic identity.
- Deleted entities remain addressable historically.
- Never use a file path as a permanent entity ID.

## Suggested ID prefixes

```text
PRJ
FEAT
REQ
ACC
RULE
CON
ARCH
DEC
ASM
UNK
RISK
TASK
TEST
RUN
EVD
DISC
CHG
AGT
SES
CHK
LSE
WSP
REL
```
