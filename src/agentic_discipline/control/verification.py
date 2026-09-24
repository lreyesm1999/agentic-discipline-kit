"""Execute approved verifiers and bind completion to current, untampered proof."""

from __future__ import annotations

import time
from typing import Any

from ..evidence import sha256_file
from ..quality import run_gate
from .contracts import ControlError, digest, encode, redact, require, uid
from .discovery import fingerprint, link_fingerprint, validate_inputs
from .intelligence import intelligence_snapshot
from .plane import Plane

JUDGMENTS = {
    "PASS": "NO_COUNTEREXAMPLE_FOUND",
    "FAIL": "COUNTEREXAMPLE_FOUND",
    "BLOCKED": "INCONCLUSIVE",
}


def _judgment(status: str) -> str:
    """A judgment verdict is named as what it is; it never becomes a deterministic PASS."""
    return JUDGMENTS[status]


def registry_for(plane: Plane) -> Any:
    from .assurance.service import registry_for as build

    return build(plane)


def binding(plane: Plane, task: dict[str, Any]) -> dict[str, Any]:
    inputs = list(
        set(task["scope"] + [p for v in task["verification"] for p in v.get("inputs", ["."])])
    )
    workspace = plane.workspace_root(task)
    # One read of the policy, so every part of the binding describes the same one.
    policy = plane.policy()
    validate_inputs(workspace, inputs)
    validate_inputs(workspace, policy["protected_paths"])
    result = {
        "files": fingerprint(workspace, inputs),
        "requirements": {i: plane.store.get(i, "entity")["version"] for i in task["requirements"]},
        "canonical_constraints": {
            c["id"]: c["version"]
            for c in plane.store.list("claim")
            if c["subject"] in task["requirements"]
            and c["authority"] in {"human", "contract"}
            and c["disposition"] == "CANONICAL"
        },
        "protected_files": fingerprint(workspace, policy["protected_paths"]),
        "dependencies": {
            i: plane.store.get(i, "task").get("proof", []) for i in task["dependencies"]
        },
        "verification": digest(task["verification"]),
        "acceptance": digest(task["acceptance"]),
        "policy": digest(policy),
    }
    if task.get("id"):
        intelligence = intelligence_snapshot(plane.root, task["id"])
        if intelligence["binding"] is not None or intelligence["reasons"]:
            result["intelligence"] = intelligence["binding"] or digest(intelligence["reasons"])
    return result


def fresh(plane: Plane, evidence: dict[str, Any], current: dict[str, Any]) -> bool:
    from .assurance.resolver import artifact_intact

    return bool(evidence["binding"] == current and artifact_intact(plane, evidence))


def assurance_stamps(plane: Plane, task: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Bind each verifier to the obligations it is being run for, before it runs."""
    from .assurance.resolver import obligation_binding, obligations_for
    from .assurance.service import enabled

    stamps: dict[str, dict[str, Any]] = {}
    if not enabled(plane):
        return stamps
    for obligation in obligations_for(plane, task["id"]):
        try:
            scoped = obligation_binding(plane, task, obligation)
        except (ControlError, OSError):
            continue
        for spec in obligation["required_verifiers"]:
            entry = stamps.setdefault(spec, {"obligation_ids": [], "obligation_bindings": {}})
            # Obligations are listed in identifier order, so each list is built sorted.
            entry["obligation_ids"].append(obligation["id"])
            entry["obligation_bindings"][obligation["id"]] = scoped
    return stamps


def changed_paths(plane: Plane, task: dict[str, Any]) -> list[str]:
    """What this task has changed since it was claimed, measured rather than reported."""

    workspace = plane.workspace_root(task)
    all_files = {**fingerprint(workspace), **link_fingerprint(workspace)}
    initial = {**task.get("initial_files", all_files), **task.get("initial_links", {})}
    return sorted(p for p in set(initial) | set(all_files) if initial.get(p) != all_files.get(p))


def check_changes(plane: Plane, task: dict[str, Any]) -> None:
    workspace = plane.workspace_root(task)
    changed = changed_paths(plane, task)
    require(
        len(changed) <= task["budget"]["max_files"],
        "BUDGET_EXCEEDED",
        "Changed-file budget exceeded",
    )
    require(
        all(
            any(s == "." or p == s or p.startswith(s.rstrip("/") + "/") for s in task["scope"])
            for p in changed
        ),
        "SCOPE_EXCEEDED",
        "Changes outside task scope",
    )
    require(
        not any(
            any(p == s or p.startswith(s + "/") for s in plane.policy()["protected_paths"])
            for p in changed
        ),
        "PROTECTED_CHANGE",
        "Protected changes require review",
    )
    changed_lines = sum(
        max(
            task.get("initial_line_counts", {}).get(p, 0),
            len((workspace / p).read_bytes().splitlines())
            if (workspace / p).is_file() and not (workspace / p).is_symlink()
            else 0,
        )
        for p in changed
    )
    require(
        changed_lines <= task["budget"]["max_lines"],
        "BUDGET_EXCEEDED",
        "Conservative changed-file line budget exceeded",
    )


def verify(
    plane: Plane, task_id: str, session: str, specs: list[str] | None = None
) -> dict[str, Any]:
    task, lease = plane.owned(task_id, session)
    selected = (
        task["verification"]
        if specs is None
        else [v for v in task["verification"] if digest(v) in set(specs)]
    )
    require(selected, "NO_VERIFIER_SELECTED", "No declared verifier matches the requested proof")
    require(
        task["state"] in {"CLAIMED", "RUNNING", "VERIFYING", "FAILED"},
        "INVALID_TRANSITION",
        "Task cannot be verified in this state",
    )
    require(
        plane.readiness(task_id)["status"] != "BLOCKED",
        "NOT_READY",
        "Readiness blockers prevent verification",
    )
    require(
        task["attempts"] <= task["budget"]["max_retries"],
        "BUDGET_EXCEEDED",
        "Retry budget exhausted; checkpoint and review",
    )
    require(not task.get("active_run"), "VERIFICATION_BUSY", "A verifier is already running")
    require(
        not (plane.directory / "evidence").is_symlink(),
        "INVALID_PATH",
        "Evidence directory must not be a symlink",
    )
    before = binding(plane, task)
    stamps = assurance_stamps(plane, task)
    known = registry_for(plane)
    check_changes(plane, task)
    workspace = plane.workspace_root(task)
    run_id = uid("RUN")
    with plane.store.transaction():
        current, run_lease = plane.owned(task_id, session)
        deadline = (
            time.time() + task["budget"]["max_runtime"] - float(task.get("runtime_used", 0)) + 30
        )
        plane.store.put(
            "lease",
            {**run_lease, "expires_at": max(run_lease["expires_at"], deadline)},
            expected=run_lease["version"],
        )
        require(not current.get("active_run"), "VERIFICATION_BUSY", "A verifier is already running")
        plane.store.put(
            "task",
            {
                **current,
                "state": "RUNNING",
                "active_run": run_id,
                "active_run_deadline": deadline,
                "attempts": current["attempts"] + 1,
            },
            expected=current["version"],
            actor=lease["agent_id"],
        )
    results = []
    runtime = float(task.get("runtime_used", 0))
    passed = False
    try:
        for spec in selected:
            remaining = task["budget"]["max_runtime"] - runtime
            require(remaining > 0, "BUDGET_EXCEEDED", "Runtime budget exhausted")
            started = time.time()
            result = run_gate(
                {"name": spec["kind"], "command": spec["command"], "timeout_seconds": remaining},
                cwd=workspace,
            )
            runtime += result.duration_seconds
            output = {
                "tool": spec["command"][0],
                "command": spec["command"],
                "exit_code": result.exit_code,
                "result": result.status,
                "started_at": started,
                "finished_at": time.time(),
                "stdout": redact(result.stdout),
                "stderr": redact(result.stderr),
                "error": redact(result.error or ""),
            }
            identifier = uid("EVD")
            artifact = plane.directory / "evidence" / (identifier + ".json")
            require(
                not artifact.parent.is_symlink(),
                "INVALID_PATH",
                "Evidence directory must not be a symlink",
            )
            artifact.parent.mkdir(exist_ok=True, mode=0o700)
            artifact.write_text(encode(output), encoding="utf-8")
            artifact.chmod(0o600)
            after = binding(plane, task)
            with plane.store.transaction():
                current_lease = plane.store.get(lease["id"], "lease")
                lease_valid = (
                    current_lease["state"] == "ACTIVE" and current_lease["expires_at"] > time.time()
                )
                stamp = stamps.get(digest(spec), {"obligation_ids": [], "obligation_bindings": {}})
                descriptor = known.get(spec["kind"])
                record = plane.store.put(
                    "evidence",
                    {
                        "id": identifier,
                        "task_id": task_id,
                        "kind": spec["kind"],
                        "verifier": digest(spec),
                        "acceptance": spec["acceptance"],
                        "run_id": run_id,
                        **stamp,
                        "evidence_class": descriptor["evidence_class"],
                        **(
                            {"judgment": _judgment(result.status)}
                            if descriptor["evidence_class"] == "AGENT_JUDGMENT"
                            else {}
                        ),
                        "run_consistent": before == after,
                        "result": "BLOCKED"
                        if result.status == "ERROR" or not lease_valid
                        else result.status,
                        "exit_code": result.exit_code,
                        "command": spec["command"],
                        "binding": before,
                        "knowledge_version": plane.store.knowledge_version,
                        "artifact_hash": sha256_file(artifact),
                        "artifact_ref": f".agentic/control/evidence/{identifier}.json",
                        "started_at": started,
                        "finished_at": output["finished_at"],
                        "stale": before != after,
                    },
                    actor=lease["agent_id"],
                )
                results.append(record)
        check_changes(plane, task)
        # A run reports what it ran, which is what VERIFYING has always meant here. Whether
        # the task holds proof for everything is answered by `completion_proof` and by the
        # obligation states, both of which completion checks.
        passed = len(results) == len(selected) and all(
            e["result"] == "PASS" and not e["stale"] for e in results
        )
    finally:
        with plane.store.transaction():
            current = plane.store.get(task_id, "task")
            if current.get("active_run") == run_id:
                plane.store.put(
                    "task",
                    {
                        **current,
                        "active_run": None,
                        "state": "VERIFYING" if passed else "FAILED",
                        "runtime_used": runtime,
                    },
                    expected=current["version"],
                    actor=lease["agent_id"],
                )
    return {"task_id": task_id, "status": "PASS" if passed else "FAIL", "evidence": results}


def completion_proof(plane: Plane, task: dict[str, Any]) -> list[dict[str, Any]]:
    require(
        plane.readiness(task["id"])["status"] != "BLOCKED",
        "NOT_READY",
        "Dependencies, knowledge, permissions or decisions are blocked",
    )
    current = binding(plane, task)
    evidence = [e for e in plane.store.list("evidence") if e["task_id"] == task["id"]]
    selected = []
    for spec in task["verification"]:
        candidates = [e for e in evidence if e["verifier"] == digest(spec)]
        require(candidates, "MISSING_EVIDENCE", "Required verifier has no execution")
        latest = max(candidates, key=lambda e: e["finished_at"])
        require(
            latest["result"] == "PASS" and not latest["stale"] and fresh(plane, latest, current),
            "STALE_OR_FAILED_EVIDENCE",
            "Latest required proof is stale, failed or tampered",
        )
        selected.append(latest)
    check_changes(plane, task)
    return selected


def assurance_gate(plane: Plane, task_id: str) -> list[dict[str, Any]]:
    """Reconcile against the real diff, then report the mandatory claims still open.

    Compiling here is what makes the completion invariant unavoidable: a task cannot
    reach completion without its obligations being derived from the change it made.
    """
    from .assurance.decision import mandatory_debt
    from .assurance.service import enabled, reconcile

    if not enabled(plane):
        return []
    reconcile(plane, task_id)
    # `reconcile` has already read this identifier as a task.
    return mandatory_debt(plane, plane.store.get(task_id))


def complete(plane: Plane, task_id: str, session: str) -> dict[str, Any]:
    # The 2.0 conditions are checked first so their diagnostics stay the ones callers
    # already act on; the transaction below then checks everything again before writing.
    preflight, _ = plane.owned(task_id, session)
    require(
        preflight["state"] == "VERIFYING", "INVALID_TRANSITION", "Only a verified task can complete"
    )
    completion_proof(plane, preflight)
    outstanding = assurance_gate(plane, task_id)
    require(
        not outstanding,
        "PROOF_DEBT",
        "Mandatory proof obligations are unresolved: "
        + "; ".join(f"{i['obligation_id']} {i['status']}" for i in outstanding),
    )
    with plane.store.transaction():
        task, lease = plane.owned(task_id, session)
        require(
            task["state"] == "VERIFYING", "INVALID_TRANSITION", "Only a verified task can complete"
        )
        proof = completion_proof(plane, task)
        checkpoints = [c for c in plane.store.list("checkpoint") if c["task_id"] == task_id]
        require(checkpoints, "CHECKPOINT_REQUIRED", "Checkpoint before completion")
        latest = max(checkpoints, key=lambda c: c["payload"]["timestamp"])
        require(
            digest(latest["payload"]) == latest["content_hash"],
            "CHECKPOINT_CORRUPT",
            "Checkpoint content does not match its hash",
        )
        if task.get("workspace_id"):
            integration = task.get("integration") or {}
            merged = (
                integration.get("status") == "PASS"
                and integration.get("merge_performed")
                and integration.get("merged_files") == fingerprint(plane.root)
                and link_fingerprint(plane.root) == link_fingerprint(plane.workspace_root(task))
            )
            # Bound once here; `completion_proof` above already refused a task whose
            # binding cannot be read.
            current = binding(plane, task)
            require(
                merged
                and binding(plane, {**task, "state": "COMPLETED"}) == current
                and integration["binding"] == digest(current),
                "INTEGRATION_REQUIRED",
                "Workspace changes need a current integration gate",
            )
        plane.store.put("lease", {**lease, "state": "RELEASED"}, expected=lease["version"])
        return plane.store.put(
            "task",
            {
                **task,
                "state": "COMPLETED",
                "completed_at": time.time(),
                "proof": [e["id"] for e in proof],
            },
            expected=task["version"],
            actor=lease["agent_id"],
        )


def proof_current(plane: Plane, task: dict[str, Any], seen: set[str] | None = None) -> bool:
    """Read live proof through dependencies; never trust a COMPLETED label alone."""
    visited = set(seen or ())
    if task["id"] in visited or task["state"] != "COMPLETED":
        return False
    visited.add(task["id"])
    if any(
        c["subject"] in task["requirements"] and c["disposition"] == "CONFLICTING"
        for c in plane.store.list("claim")
    ):
        return False
    try:
        current = binding(plane, task)
        proof = [plane.store.get(i, "evidence") for i in task.get("proof", [])]
        return bool(
            {e["verifier"] for e in proof} == {digest(v) for v in task["verification"]}
            and all(
                e["result"] == "PASS" and not e["stale"] and fresh(plane, e, current) for e in proof
            )
            and all(
                plane.store.get(i, "entity")["lifecycle"] == "ACTIVE"
                and not plane.store.get(i, "entity").get("stale")
                for i in task["requirements"]
            )
            and all(
                proof_current(plane, plane.store.get(i, "task"), visited)
                for i in task["dependencies"]
            )
        )
    except (ControlError, OSError):
        return False


def invalidate(plane: Plane) -> dict[str, Any]:
    invalidated = []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for evidence in plane.store.list("evidence"):
        grouped.setdefault(evidence["task_id"], []).append(evidence)
    for task in plane.store.list("task"):
        if not grouped.get(task["id"]):
            continue
        try:
            current = binding(plane, task)
        except (OSError, RuntimeError, ControlError):
            current = {}
        with plane.store.transaction():
            for evidence in grouped[task["id"]]:
                if not evidence["stale"] and not fresh(plane, evidence, current):
                    plane.store.put(
                        "evidence", {**evidence, "stale": True}, expected=evidence["version"]
                    )
                    invalidated.append(evidence["id"])
            if task["state"] == "COMPLETED" and not proof_current(plane, task):
                plane.store.put(
                    "task", {**task, "state": "NEEDS_REVALIDATION"}, expected=task["version"]
                )
    with plane.store.transaction():
        for claim in plane.store.list("claim"):
            if claim["disposition"] != "CANONICAL":
                continue
            subject = plane.store.get(claim["subject"], "entity")
            stale = (
                subject["lifecycle"] != "ACTIVE"
                or subject.get("stale")
                or any(
                    plane.store.get(i, "evidence")["stale"] for i in claim.get("evidence_refs", [])
                )
            )
            if stale:
                plane.store.bump()
                plane.store.put(
                    "claim", {**claim, "disposition": "STALE"}, expected=claim["version"]
                )
    return {"invalidated": invalidated}
