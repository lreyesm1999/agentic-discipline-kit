# Trust boundary and limitations

The initial deployment is one trusted OS user on a local filesystem. SQLite leases
coordinate cooperating clients; an administrator who can edit source, SQLite or the
Python process is outside that boundary. Audit hashes detect accidental or uncoordinated
tampering, not an administrator rebuilding the database and hash chain. Network-mounted
SQLite, hosted multi-tenancy, remote authentication and deployment are not implemented.

Approved verifiers run without a shell through the existing executor. Approval grants
the specified local command execution capability. This is **not an OS sandbox**: a
Python test can itself invoke other programs or use its environment. Network/production
flags and external-call/cost budgets express the contract; this local executor has no
network proxy or billing meter. Do not use it to execute hostile code. Enforce external
network, filesystem and credential isolation in the host when those guarantees are
required. Measured enforcement covers argv approval, ownership, runtime/retries,
changed files/lines, declared scope, protected paths and proof freshness.

File fingerprints include measured project content and generated build/dist inputs;
known secrets, dependency caches, control-state files and runtime output stores are
excluded. Explicit symlink inputs and symlinks inside a measured scope are rejected.
Verifiers that rely on an external database, clock, network, installed dependencies or
excluded cache require an environment-specific verifier and fresh run. Source hashes
alone cannot establish freshness for unmeasured external state. Narrow `inputs` lists
are an owner-reviewed declaration of the complete dependency set, not automatically
inferred read tracing. The default is the whole measured project.

Secret redaction rejects recognized credential keys/patterns and removes recognized
values from outputs/excerpts. It cannot recognize every arbitrary secret; this is not
permission to ingest credentials. Output artifacts can contain private application
information and remain local. An agent checkpoint is a continuity record, not proof
that its narrative statements are correct.

Planning audit deterministically checks structured contracts and returns an ask-last
resolution order. It does not invent product requirements, autonomously research the
internet, or call an LLM. The coding agent uses repository sources to resolve the gaps.
Discovery is bounded static observation: Python declarations have qualified source
locations and containment links; other languages currently use file observations and
existing stack profiles. Runtime behavior and cross-language call resolution remain
UNKNOWN until supported by actual verifiers. Same-name Python declarations retain
separate occurrence identities; semantic symbol moves need review.

Context preserves required contracts, human decisions, failure outputs and checkpoint
content. An insufficient budget is rejected rather than silently truncating them.
Token counts are byte-based estimates. Optional source excerpts are capped, require
source confirmation, and do not override higher-authority requirements.

Parallelism is conservative: path overlap conflicts, shared declared boundaries
serialize, and HIGH/CRITICAL tasks require review. Fast-forward integration and
conflict-aborting rebase are supported; semantic conflict resolution is not inferred
from a clean Git merge. Cleanup preserves branches and refuses dirty active work.

The 2.0.0 release is stable within this boundary and no further. Its release gates —
human acceptance, the supported platform CI matrix (Linux and Windows), mutation
disposition and release evidence — are recorded in VALIDATION.md; absence of a result
is not PASS. macOS is not a supported platform until CI runs the suite there.
