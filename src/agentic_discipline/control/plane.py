"""Application services shared by CLI, MCP and read-only console."""

from __future__ import annotations

import hashlib
import json
import secrets
import shutil
import time
from pathlib import Path
from typing import Any

from .contracts import (
    TRANSITIONS,
    ControlError,
    digest,
    encode,
    require,
    safe_data,
    task_contract,
    uid,
)
from .discovery import fingerprint, git, line_counts, link_fingerprint, scan
from .knowledge import Knowledge
from .store import Store


def state_dir(root: Path) -> Path:
    for path in (root / ".agentic", root / ".agentic" / "control"):
        require(not path.is_symlink(), "INVALID_PATH", "Control state cannot follow symlinks")
    return root / ".agentic" / "control"


def adopt(root: Path, dry_run: bool = False) -> dict[str, Any]:
    root = root.resolve()
    target = state_dir(root)
    report = scan(root)
    report["dry_run"] = dry_run
    report["writes"] = [".agentic/control/state.db"]
    if dry_run:
        return report
    if (target / "state.db").exists():
        with Plane(root) as plane:
            return {"already_adopted": True, **plane.status()}
    require(
        not target.exists(),
        "UNMANAGED_STATE",
        "Control directory already exists; inspect it before adoption",
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / ("adopt-" + secrets.token_hex(8))
    staging.mkdir(mode=0o700)
    try:
        with Store(staging / "state.db", create=True) as store:
            with store.transaction():
                store.put(
                    "project",
                    {
                        "name": root.name,
                        "root": str(root),
                        "baseline_commit": report["commit"],
                        "baseline_fingerprint": report["fingerprint"],
                        "coverage": report["coverage"],
                        "stacks": report["stacks"],
                    },
                )
                store.put(
                    "policy",
                    {
                        "allowed_commands": [],
                        "protected_paths": [
                            ".agentic",
                            "AGENTS.md",
                            "MASTER_PROMPT.md",
                            "agentic.config.json",
                            "agentic.config.example.json",
                            "schemas",
                            "skills",
                            "disciplines",
                            "specs",
                            "acceptance",
                            "architecture",
                            "policies",
                            ".github/workflows",
                        ],
                        "max_lease_seconds": 3600,
                        "network": False,
                        "production": False,
                    },
                )
            _index(store, report)
            store.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        (staging / "state.db").chmod(0o600)
        staging.rename(target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {
        "adopted": True,
        "coverage": report["coverage"],
        "stacks": report["stacks"],
        "files": len(report["files"]),
        "runtime": "UNKNOWN",
        "writes": report["writes"],
    }


def _index(store: Store, report: dict[str, Any]) -> dict[str, Any]:
    old = {e["source_ref"]: e for e in store.list("entity") if e.get("type") == "file"}
    names = {f["path"] for f in report["files"]}
    removed = {
        name: e for name, e in old.items() if name not in names and e["lifecycle"] == "ACTIVE"
    }
    changed: list[str] = []
    symbols_by_file: dict[str, list[dict[str, Any]]] = {}
    for entity in store.list("entity"):
        if entity.get("type") == "symbol":
            symbols_by_file.setdefault(entity["file_id"], []).append(entity)
    with store.transaction():
        store.bump()
        for item in report["files"]:
            previous = old.get(item["path"])
            if not previous:
                renames = [
                    e for e in removed.values() if e.get("content_hash") == item["content_hash"]
                ]
                if len(renames) == 1:
                    previous = renames[0]
                    removed.pop(previous["source_ref"])
            if (
                previous
                and previous.get("content_hash") == item["content_hash"]
                and previous["source_ref"] == item["path"]
            ):
                continue
            changed.append(item["path"])
            payload = {
                "graph": "code",
                "type": "file",
                "name": item["path"],
                "source_ref": item["path"],
                "authority": "code",
                "confidence": 1,
                "observation": "OBSERVED",
                "lifecycle": previous["lifecycle"] if previous else "ACTIVE",
                "stale": False,
                **item,
            }
            if previous:
                payload["id"] = previous["id"]
            indexed = store.put(
                "entity", payload, expected=previous["version"] if previous else None
            )
            _index_symbols(store, indexed, symbols_by_file.get(indexed["id"], []))
        for name, previous in removed.items():
            changed.append(name)
            store.put(
                "entity",
                {
                    **previous,
                    "stale": True,
                    "lifecycle": "HISTORICAL",
                    "lifecycle_reason": "source removed; preserved for history",
                },
                expected=previous["version"],
            )
            _index_symbols(
                store,
                {**previous, "symbols": [], "lifecycle": "HISTORICAL"},
                symbols_by_file.get(previous["id"], []),
            )
        project = store.list("project")[0]
        store.put(
            "project",
            {
                **project,
                "coverage": report["coverage"],
                "last_fingerprint": report["fingerprint"],
                "last_commit": report["commit"],
                "last_reconcile": time.time(),
            },
            expected=project["version"],
        )
        store.event(
            "local",
            "discovery.index",
            {"changed_paths": changed, "fingerprint": report["fingerprint"]},
        )
    return {
        "changed_paths": changed,
        "knowledge_version": store.knowledge_version,
        "coverage": report["coverage"],
    }


def _index_symbols(store: Store, source: dict[str, Any], previous: list[dict[str, Any]]) -> None:
    old = {(s["name"], s["symbol_type"], s["occurrence"]): s for s in previous}
    present = set()
    counts: dict[tuple[str, str], int] = {}
    for symbol in source["symbols"]:
        if symbol["type"] == "Import":
            continue
        declaration = (symbol["name"], symbol["type"])
        occurrence = counts.get(declaration, 0)
        counts[declaration] = occurrence + 1
        key = (*declaration, occurrence)
        prior = old.get(key)
        present.add(key)
        node = store.put(
            "entity",
            {
                **({"id": prior["id"]} if prior else {}),
                "graph": "code",
                "type": "symbol",
                "name": symbol["name"],
                "symbol_type": symbol["type"],
                "occurrence": occurrence,
                "file_id": source["id"],
                "line": symbol["line"],
                "source_ref": source["source_ref"],
                "content_hash": source["content_hash"],
                "authority": "code",
                "observation": "OBSERVED",
                "confidence": 1,
                "lifecycle": prior["lifecycle"] if prior else source["lifecycle"],
                "stale": False,
            },
            expected=prior["version"] if prior else None,
        )
        store.db.execute(
            "INSERT OR IGNORE INTO edges VALUES (?,?,?,?)",
            (uid("EDGE"), source["id"], node["id"], "contains"),
        )
    for key, prior in old.items():
        if key not in present and prior["lifecycle"] == "ACTIVE":
            store.put(
                "entity",
                {
                    **prior,
                    "lifecycle": "HISTORICAL",
                    "stale": True,
                    "lifecycle_reason": "symbol absent from observed source",
                },
                expected=prior["version"],
            )


class Plane:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.directory = state_dir(self.root)
        self.store = Store(self.directory / "state.db")
        self.knowledge = Knowledge(self.store)

    def __enter__(self) -> Plane:
        return self

    def __exit__(self, *args: Any) -> None:
        self.store.close()

    def policy(self) -> dict[str, Any]:
        return self.store.list("policy")[0]

    def approve_command(self, command: list[str]) -> dict[str, Any]:
        require(
            command and all(isinstance(x, str) and x for x in command),
            "INVALID_COMMAND",
            "Use argv",
        )
        safe_data(command)
        with self.store.transaction():
            policy = self.policy()
            commands = policy["allowed_commands"]
            if command not in commands:
                commands.append(command)
            return self.store.put(
                "policy",
                {**policy, "allowed_commands": commands},
                expected=policy["version"],
                actor="local-human",
            )

    def create_task(self, contract: dict[str, Any]) -> dict[str, Any]:
        task_contract(contract)
        require(
            not ({"state", "version", "id", "workspace_id", "integration"} & contract.keys()),
            "INVALID_TASK",
            "Execution state is server-owned",
        )
        for identifier in contract["requirements"]:
            requirement = self.store.get(identifier, "entity")
            require(
                requirement["lifecycle"] == "ACTIVE" and not requirement.get("stale"),
                "STALE_REQUIREMENT",
                "Task refers to inactive or stale knowledge",
            )
        for identifier in contract["dependencies"]:
            self.store.get(identifier, "task")
        with self.store.transaction():
            return self.store.put(
                "task",
                {
                    **contract,
                    "state": "PLANNED",
                    "knowledge_version": self.store.knowledge_version,
                    "created_at": time.time(),
                    "attempts": 0,
                    "blocker": None,
                    "workspace_id": None,
                },
            )

    def audit_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        # The contract allows these lists to be empty, so stating one covers it.
        may_be_empty = {"out_of_scope", "dependencies", "boundaries", "context"}
        dimensions = {
            k: "COVERED"
            if plan.get(k) or (k in may_be_empty and isinstance(plan.get(k), list))
            else "MISSING"
            for k in (
                "objective",
                "scope",
                "out_of_scope",
                "acceptance",
                "dependencies",
                "boundaries",
                "context",
                "verification",
                "required_evidence",
                "rollback",
                "definition_of_done",
                "risk",
                "budget",
            )
        }
        issues = []
        try:
            task_contract(plan)
        except ControlError as exc:
            issues.append({"code": exc.code, "message": str(exc)})
        return {
            "dimensions": dimensions,
            "issues": issues,
            "status": "BLOCKED" if issues else "READY",
            "ask_last": [
                "canonical knowledge",
                "source",
                "tests",
                "current docs",
                "history",
                "reversible convention",
                "experiment",
                "human decision",
            ],
            "next_action": "Resolve missing contract fields from project sources"
            if issues
            else "Create task",
        }

    def readiness(self, task_id: str) -> dict[str, Any]:
        task = self.store.get(task_id, "task")
        reasons = []
        for identifier in task["dependencies"]:
            from .verification import proof_current

            if not proof_current(self, self.store.get(identifier, "task")):
                reasons.append({"type": "dependency", "id": identifier})
        for identifier in task["requirements"]:
            entity = self.store.get(identifier, "entity")
            if entity["lifecycle"] != "ACTIVE" or entity.get("stale"):
                reasons.append({"type": "knowledge", "id": identifier})
        policy = self.policy()
        for verifier in task["verification"]:
            if verifier["command"] not in policy["allowed_commands"]:
                reasons.append({"type": "unapproved_command", "command": verifier["command"]})
        conflicts = [
            c["id"]
            for c in self.store.list("claim")
            if c["subject"] in task["requirements"] and c["disposition"] == "CONFLICTING"
        ]
        reasons.extend({"type": "conflict", "id": c} for c in conflicts)
        if task.get("blocker"):
            reasons.append({"type": "human", "reason": task["blocker"]})
        return {
            "task_id": task_id,
            "status": "BLOCKED"
            if reasons
            else "READY_WITH_MANAGED_UNCERTAINTY"
            if task.get("assumptions")
            else "READY",
            "reasons": reasons,
            "assumptions": task.get("assumptions", []),
        }

    def ready(self, task_id: str) -> dict[str, Any]:
        with self.store.transaction():
            task = self.store.get(task_id, "task")
            require(
                task["state"] in {"PLANNED", "BLOCKED", "FAILED", "NEEDS_REVALIDATION", "READY"},
                "INVALID_TRANSITION",
                "Task cannot become ready",
            )
            require(
                self.readiness(task_id)["status"] != "BLOCKED",
                "NOT_READY",
                "Readiness blockers remain",
            )
            return self.store.put(
                "task", {**task, "state": "READY", "active_run": None}, expected=task["version"]
            )

    def resolve_blocker(self, task_id: str, decision: str) -> dict[str, Any]:
        require(
            bool(decision.strip()),
            "DECISION_REQUIRED",
            "Record the decision that resolves the blocker",
        )
        with self.store.transaction():
            task = self.store.get(task_id, "task")
            require(
                task["state"] == "BLOCKED" and task.get("blocker"),
                "NOT_BLOCKED",
                "Task has no human blocker",
            )
            self.store.put(
                "decision",
                {
                    "task_id": task_id,
                    "question": task["blocker"],
                    "decision": decision,
                    "state": "DECIDED",
                    "authority": "human",
                },
                actor="local-owner",
            )
            return self.store.put(
                "task", {**task, "blocker": None}, expected=task["version"], actor="local-owner"
            )

    def transition(self, task_id: str, state: str, reason: str) -> dict[str, Any]:
        require(
            state in {"CANCELLED", "SUPERSEDED"} and bool(reason.strip()),
            "INVALID_TRANSITION",
            "Cancellation or supersession needs a reason",
        )
        with self.store.transaction():
            task = self.store.get(task_id, "task")
            require(
                state in TRANSITIONS[task["state"]] and not task.get("active_run"),
                "INVALID_TRANSITION",
                "Task cannot transition while a verifier is active or after terminal disposition",
            )
            for lease in self.store.list("lease"):
                if lease["task_id"] == task_id and lease["state"] == "ACTIVE":
                    self.store.put(
                        "lease", {**lease, "state": "REVOKED"}, expected=lease["version"]
                    )
            return self.store.put(
                "task",
                {**task, "state": state, "disposition_reason": reason},
                expected=task["version"],
                actor="local-owner",
            )

    def join(self, name: str, capabilities: list[str]) -> dict[str, Any]:
        allowed_caps = {
            "code",
            "terminal",
            "frontend",
            "backend",
            "database",
            "security",
            "testing",
            "documentation",
            "browser",
            "code_editing",
        }
        require(
            bool(name.strip()) and bool(capabilities) and set(capabilities) <= allowed_caps,
            "INVALID_AGENT",
            "Name and supported capabilities required",
        )
        token = secrets.token_urlsafe(32)
        with self.store.transaction():
            agent = self.store.put(
                "agent",
                {
                    "name": name,
                    "capabilities": capabilities,
                    "session_hash": hashlib.sha256(token.encode()).hexdigest(),
                    "joined_at": time.time(),
                    "heartbeat_at": time.time(),
                    "status": "ONLINE",
                },
            )
        return {"id": agent["id"], "name": name, "session": token}

    def authenticate(self, token: str) -> dict[str, Any]:
        hashed = hashlib.sha256(token.encode()).hexdigest()
        for agent in self.store.list("agent"):
            if secrets.compare_digest(agent["session_hash"], hashed):
                return agent
        raise ControlError("UNAUTHORIZED", "Unknown agent session")

    def _expire(self) -> None:
        for lease in self.store.list("lease"):
            if lease["state"] == "ACTIVE" and lease["expires_at"] <= time.time():
                running = self.store.get(lease["task_id"], "task")
                if (
                    running.get("active_run")
                    and running.get("active_run_deadline", 0) > time.time()
                ):
                    continue
                self.store.put("lease", {**lease, "state": "EXPIRED"}, expected=lease["version"])
                task = self.store.get(lease["task_id"], "task")
                if task["state"] in {"CLAIMED", "RUNNING", "VERIFYING", "FAILED"}:
                    self.store.put(
                        "task",
                        {**task, "state": "READY", "active_run": None},
                        expected=task["version"],
                    )

    def claim(self, task_id: str, session: str, seconds: int = 300) -> dict[str, Any]:
        agent = self.authenticate(session)
        require(
            type(seconds) is int and 0 < seconds <= self.policy()["max_lease_seconds"],
            "INVALID_LEASE",
            "Invalid lease lifetime",
        )
        with self.store.transaction():
            self._expire()
            task = self.store.get(task_id, "task")
            require(
                task["state"] == "READY" and self.readiness(task_id)["status"] != "BLOCKED",
                "NOT_READY",
                "Task is not available",
            )
            require(
                set(task.get("capabilities", [])) <= set(agent["capabilities"]),
                "CAPABILITY_MISMATCH",
                "Agent lacks task capabilities",
            )
            require(
                not any(
                    item["task_id"] == task_id and item["state"] == "ACTIVE"
                    for item in self.store.list("lease")
                ),
                "LEASE_CONFLICT",
                "Task already has an owner",
            )
            from .workspaces import parallel_safety

            for active in self.store.list("lease"):
                if active["state"] == "ACTIVE":
                    other = self.store.get(active["task_id"], "task")
                    require(
                        task.get("workspace_id")
                        and other.get("workspace_id")
                        and parallel_safety(task, other)["status"] == "SAFE_PARALLEL",
                        "PARALLEL_CONFLICT",
                        "Concurrent work requires isolated workspaces and disjoint contracts",
                    )
            workspace = self.workspace_root(task)
            baseline = task.get("initial_files", fingerprint(workspace))
            self.store.put(
                "task",
                {
                    **task,
                    "state": "CLAIMED",
                    "initial_files": baseline,
                    "initial_links": task.get("initial_links", link_fingerprint(workspace)),
                    "initial_line_counts": task.get(
                        "initial_line_counts", line_counts(workspace, list(fingerprint(workspace)))
                    ),
                },
                expected=task["version"],
                actor=agent["id"],
            )
            return self.store.put(
                "lease",
                {
                    "task_id": task_id,
                    "agent_id": agent["id"],
                    "acquired_at": time.time(),
                    "heartbeat_at": time.time(),
                    "expires_at": time.time() + seconds,
                    "state": "ACTIVE",
                },
                actor=agent["id"],
            )

    def owned(self, task_id: str, session: str) -> tuple[dict[str, Any], dict[str, Any]]:
        agent = self.authenticate(session)
        leases = [
            item
            for item in self.store.list("lease")
            if item["task_id"] == task_id
            and item["agent_id"] == agent["id"]
            and item["state"] == "ACTIVE"
            and item["expires_at"] > time.time()
        ]
        require(len(leases) == 1, "LEASE_LOST", "No active lease owned by this agent")
        return self.store.get(task_id, "task"), leases[0]

    def heartbeat(self, task_id: str, session: str, seconds: int = 300) -> dict[str, Any]:
        require(
            type(seconds) is int and 0 < seconds <= self.policy()["max_lease_seconds"],
            "INVALID_LEASE",
            "Invalid lease lifetime",
        )
        with self.store.transaction():
            _, lease = self.owned(task_id, session)
            agent = self.store.get(lease["agent_id"], "agent")
            self.store.put(
                "agent", {**agent, "heartbeat_at": time.time()}, expected=agent["version"]
            )
            return self.store.put(
                "lease",
                {**lease, "heartbeat_at": time.time(), "expires_at": time.time() + seconds},
                expected=lease["version"],
            )

    def release(self, task_id: str, session: str, blocker: str | None = None) -> dict[str, Any]:
        with self.store.transaction():
            task, lease = self.owned(task_id, session)
            require(
                not task.get("active_run"),
                "VERIFICATION_BUSY",
                "Wait for the active verifier before releasing ownership",
            )
            self.store.put("lease", {**lease, "state": "RELEASED"}, expected=lease["version"])
            return self.store.put(
                "task",
                {**task, "state": "BLOCKED" if blocker else "READY", "blocker": blocker},
                expected=task["version"],
            )

    def checkpoint(self, task_id: str, session: str, data: dict[str, Any]) -> dict[str, Any]:
        required = {
            "completed_work",
            "modified_files",
            "commands_run",
            "tests_run",
            "test_results",
            "failures",
            "discoveries",
            "assumptions",
            "pending_issues",
            "current_hypothesis",
            "next_action",
        }
        require(
            required <= data.keys() and bool(data["next_action"]),
            "INVALID_CHECKPOINT",
            "Checkpoint lacks resumable context",
        )
        safe_data(data)
        with self.store.transaction():
            task, lease = self.owned(task_id, session)
            workspace = self.workspace_root(task)
            payload = {
                **data,
                "task_id": task_id,
                "agent_id": lease["agent_id"],
                "objective": task["objective"],
                "execution_phase": task["state"],
                "branch": git(workspace, ["branch", "--show-current"]),
                "workspace": str(workspace),
                "commit": git(workspace, ["rev-parse", "HEAD"]),
                "knowledge_version": self.store.knowledge_version,
                "fingerprint": digest(fingerprint(workspace)),
                "evidence_refs": [
                    e["id"] for e in self.store.list("evidence") if e["task_id"] == task_id
                ],
                "timestamp": time.time(),
            }
            return self.store.put(
                "checkpoint",
                {"task_id": task_id, "payload": payload, "content_hash": digest(payload)},
            )

    def workspace_root(self, task: dict[str, Any]) -> Path:
        if (
            task["state"] == "COMPLETED"
            and task.get("integration")
            and task["integration"].get("merge_performed")
        ):
            return self.root
        if not task.get("workspace_id"):
            return self.root
        workspace = self.store.get(task["workspace_id"], "workspace")
        if workspace["status"] == "REMOVED" and task.get("integration", {}).get("merge_performed"):
            return self.root
        path = Path(workspace["path"])
        require(
            path.parent == self.directory / "worktrees"
            and path.is_dir()
            and not path.is_symlink()
            and not path.parent.is_symlink(),
            "WORKSPACE_LOST",
            "Task workspace is missing; checkpoint retained",
        )
        return path

    def context(self, task_id: str, budget: int = 16000) -> dict[str, Any]:
        task = self.store.get(task_id, "task")
        checkpoints = [c for c in self.store.list("checkpoint") if c["task_id"] == task_id]
        checkpoint = (
            max(checkpoints, key=lambda c: c["payload"]["timestamp"]) if checkpoints else None
        )
        if checkpoint:
            require(
                digest(checkpoint["payload"]) == checkpoint["content_hash"],
                "CHECKPOINT_CORRUPT",
                "Checkpoint content does not match its hash",
            )
        requirements = [self.store.get(i, "entity") for i in task["requirements"]]
        active = [
            e
            for e in self.store.list("entity")
            if e["lifecycle"] == "ACTIVE" and not e.get("stale")
        ]
        references = []
        for reference in task["context"]:
            matches = [e for e in active if e["id"] == reference or e["source_ref"] == reference]
            require(
                matches, "MISSING_CONTEXT", f"Required context is missing or stale: {reference}"
            )
            references.extend(matches)
        protected_decisions = [
            e
            for e in active
            if e["graph"] in {"decision", "architecture"}
            and e["authority"] in {"human", "contract"}
        ]
        latest_evidence: dict[str, dict[str, Any]] = {}
        for evidence in self.store.list("evidence"):
            latest = latest_evidence.get(evidence["verifier"])
            if evidence["task_id"] == task_id and (
                latest is None or evidence["finished_at"] > latest["finished_at"]
            ):
                latest_evidence[evidence["verifier"]] = evidence
        failures = []
        for evidence in latest_evidence.values():
            if evidence["result"] == "PASS":
                continue
            artifact = self.directory / "evidence" / (evidence["id"] + ".json")
            require(
                artifact.is_file()
                and not artifact.is_symlink()
                and not artifact.parent.is_symlink()
                and hashlib.sha256(artifact.read_bytes()).hexdigest() == evidence["artifact_hash"],
                "EVIDENCE_CORRUPT",
                "Failure output was changed or removed",
            )
            failures.append(
                {"evidence": evidence, "output": json.loads(artifact.read_text(encoding="utf-8"))}
            )
        require(
            all(e["lifecycle"] == "ACTIVE" and not e.get("stale") for e in requirements),
            "STALE_CONTEXT",
            "Required knowledge is not current",
        )
        mandatory = {
            "task": {
                k: v
                for k, v in task.items()
                if k not in {"initial_files", "initial_links", "initial_line_counts", "integration"}
            },
            "integration": {
                k: v for k, v in (task.get("integration") or {}).items() if k != "merged_files"
            },
            "requirements": requirements,
            "required_context": references,
            "protected_decisions": protected_decisions,
            "decisions": [d for d in self.store.list("decision") if d.get("task_id") == task_id],
            "checkpoint": checkpoint,
            "policy": self.policy(),
            "current_failures": failures,
        }
        used = len(encode(mandatory).encode())
        require(
            type(budget) is int and used <= budget <= 1000000,
            "CONTEXT_BUDGET",
            f"Mandatory context needs {used} bytes; never truncate it",
        )
        sources = []
        for entity in active:
            if entity["graph"] == "code" and any(
                s == "."
                or entity["source_ref"] == s
                or entity["source_ref"].startswith(s.rstrip("/") + "/")
                for s in task["scope"]
            ):
                size = len(encode(entity).encode())
                if used + size <= budget:
                    sources.append(entity)
                    used += size
        return {
            "mandatory": mandatory,
            "sources": sources,
            "audit": {
                "bytes": used,
                "budget_bytes": budget,
                "estimated_tokens": (used + 3) // 4,
                "mandatory_bytes": len(encode(mandatory).encode()),
                "estimate_only": True,
            },
            "source_confirmation_required": True,
        }

    def resume(self, task_id: str, session: str, budget: int = 16000) -> dict[str, Any]:
        task, _ = self.owned(task_id, session)
        context = self.context(task_id, budget)
        checkpoint = context["mandatory"]["checkpoint"]
        workspace = self.workspace_root(task)
        return {
            **context,
            "baseline_changed": bool(
                checkpoint
                and checkpoint["payload"]["fingerprint"] != digest(fingerprint(workspace))
            ),
            "workspace": str(workspace),
        }

    def reconcile(self) -> dict[str, Any]:
        from .verification import invalidate

        report = scan(self.root)
        current = self.store.list("project")[0]
        if report["fingerprint"] == current.get("last_fingerprint"):
            return {
                "changed_paths": [],
                "knowledge_version": self.store.knowledge_version,
                **invalidate(self),
            }
        result = _index(self.store, report)

        return {**result, **invalidate(self)}

    def status(self) -> dict[str, Any]:
        from .verification import invalidate

        invalidate(self)
        with self.store.transaction():
            self._expire()
        tasks = self.store.list("task")
        entities = self.store.list("entity")
        evidence = self.store.list("evidence")
        requirements = [
            e for e in entities if e["graph"] == "requirement" and e["lifecycle"] == "ACTIVE"
        ]
        verified_requirements = {
            identifier
            for task in tasks
            if task["state"] == "COMPLETED"
            for identifier in task["requirements"]
        }
        claims = self.store.list("claim")
        return {
            "project": self.store.list("project")[0],
            "knowledge_version": self.store.knowledge_version,
            "task_counts": {
                state: sum(t["state"] == state for t in tasks)
                for state in sorted({t["state"] for t in tasks})
            },
            "tasks": tasks,
            "agents": [
                {k: v for k, v in a.items() if k != "session_hash"}
                for a in self.store.list("agent")
            ],
            "leases": self.store.list("lease"),
            "evidence": evidence,
            "requirements": requirements,
            "evolution": [
                e for e in entities if e["lifecycle"] != "ACTIVE" or e["graph"] == "evolution"
            ],
            "metrics": {
                "verification": {
                    "verified": sum(e["id"] in verified_requirements for e in requirements),
                    "total": len(requirements),
                },
                "evidence_currency": {
                    "current": sum(not e["stale"] for e in evidence),
                    "total": len(evidence),
                },
                "decision_debt": {
                    "task_blockers": sum(bool(t.get("blocker")) for t in tasks),
                    "conflicting_claims": sum(c["disposition"] == "CONFLICTING" for c in claims),
                },
            },
            "knowledge": {
                "active": sum(e["lifecycle"] == "ACTIVE" for e in entities),
                "stale": sum(bool(e.get("stale")) for e in entities),
                "historical": sum(e["lifecycle"] != "ACTIVE" for e in entities),
            },
            "claims": claims,
            "decisions": [e for e in entities if e["graph"] == "decision"]
            + self.store.list("decision"),
            "audit": self.store.audit(),
            "freshness_note": "Proof is checked against current measured files and artifacts. Reconcile also refreshes discovery.",
        }
