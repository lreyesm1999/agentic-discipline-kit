"""Decide what current evidence actually proves, one obligation at a time.

Freshness is bound to the paths, requirements, policy and verifiers that obligation
depends on, so an unrelated edit does not invalidate it and a relevant edit always does.
"""

from __future__ import annotations

import json
from typing import Any

from ...evidence import sha256_file
from ..contracts import digest
from ..discovery import fingerprint, validate_inputs
from .model import RESOLVED


def artifact_intact(plane: Any, evidence: dict[str, Any]) -> bool:
    artifact = plane.directory / "evidence" / (evidence["id"] + ".json")
    return bool(
        artifact.is_file()
        and not artifact.parent.is_symlink()
        and not artifact.is_symlink()
        and sha256_file(artifact) == evidence["artifact_hash"]
    )


def outcome_matches(plane: Any, evidence: dict[str, Any]) -> bool:
    """The verdict must be the one the run itself wrote, not the one its row now says.

    Editing the record to claim a pass is the cheapest way to hide a failure, so the
    hashed artefact - which the row cannot change without breaking its own hash - has the
    final word. BLOCKED is the one verdict the plane assigns itself, when a run finishes
    outside a valid lease or cannot reach a verdict at all.
    """
    artifact = plane.directory / "evidence" / (evidence["id"] + ".json")
    try:
        recorded = json.loads(artifact.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(recorded, dict) or recorded.get("exit_code") != evidence["exit_code"]:
        return False
    return evidence["result"] in {recorded.get("result"), "BLOCKED"}


def obligation_binding(
    plane: Any, task: dict[str, Any], obligation: dict[str, Any]
) -> dict[str, Any]:
    """Only what this claim depends on. Missing path information falls back to the scope."""
    paths = obligation["affected_paths"] or list(task["scope"])
    workspace = plane.workspace_root(task)
    policy = plane.policy()
    validate_inputs(workspace, paths)
    validate_inputs(workspace, policy["protected_paths"])
    return {
        "files": fingerprint(workspace, paths),
        "protected_files": fingerprint(workspace, policy["protected_paths"]),
        "requirements": {
            i: plane.store.get(i, "entity")["version"]
            for i in obligation["origin"]["requirement_ids"]
        },
        "acceptance": digest(
            [task["acceptance"][i] for i in obligation["origin"]["acceptance_ids"]]
        ),
        "verifiers": digest(sorted(obligation["required_verifiers"])),
        "claim": digest(obligation["claim"]),
        "policy": digest(policy),
    }


def run_consistent(evidence: dict[str, Any]) -> bool:
    """A run whose own inputs moved underneath it never proves anything."""
    recorded = evidence.get("run_consistent")
    return bool(recorded) if recorded is not None else not evidence.get("stale")


def matches(evidence: dict[str, Any], obligation: dict[str, Any]) -> bool:
    if obligation["id"] in evidence.get("obligation_ids", []):
        return True
    # Evidence recorded before this plan existed still proves an acceptance criterion,
    # because that binding is the task contract's own.
    return obligation["derivation"] == "CONTRACT" and bool(
        set(obligation["origin"]["acceptance_ids"]) & set(evidence.get("acceptance", []))
    )


def current_for(
    plane: Any,
    evidence: dict[str, Any],
    obligation: dict[str, Any],
    binding: dict[str, Any],
    task_binding: dict[str, Any],
) -> bool:
    if not run_consistent(evidence) or not artifact_intact(plane, evidence):
        return False
    if not outcome_matches(plane, evidence):
        return False
    recorded = (evidence.get("obligation_bindings") or {}).get(obligation["id"])
    # Without a per-obligation binding the only honest test is the conservative one the
    # 2.0 record carries.
    if recorded is not None:
        return bool(recorded == binding)
    return bool(evidence["binding"] == task_binding)


def resolve(
    plane: Any,
    task: dict[str, Any],
    obligation: dict[str, Any],
    *,
    evidence: list[dict[str, Any]] | None = None,
    task_binding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if obligation["status"] == "WAIVED":
        return {
            "obligation_id": obligation["id"],
            "status": "WAIVED",
            "reason": "an owner waiver is recorded for this obligation",
            "current": [],
            "stale": [],
            "superseded": [],
            "missing_verifiers": [],
        }
    from ..verification import binding as task_level_binding

    records = (
        evidence
        if evidence is not None
        else [e for e in plane.store.list("evidence") if e["task_id"] == task["id"]]
    )
    conservative = task_binding if task_binding is not None else task_level_binding(plane, task)
    scoped = obligation_binding(plane, task, obligation)
    required = set(obligation["required_verifiers"])
    related = [e for e in records if matches(e, obligation)]
    # Only the verifiers this claim requires now speak for it. A verdict from a route the
    # plan escalated away from stays in the ledger as superseded, never as proof.
    matched = [e for e in related if not required or e["verifier"] in required]
    current = [e for e in matched if current_for(plane, e, obligation, scoped, conservative)]
    stale = [e for e in matched if e not in current]
    results = {e["result"] for e in current}
    # Deterministic dominance at resolution time as well as at selection time: while a
    # deterministic verifier can reach this claim, judgment evidence does not close it.
    dominated = bool(obligation.get("plan", {}).get("deterministic_available"))
    proven = {
        e["verifier"]
        for e in current
        if e["result"] == "PASS" and not (dominated and e.get("evidence_class") == "AGENT_JUDGMENT")
    }
    human = bool(obligation.get("plan", {}).get("human_required"))
    if "FAIL" in results and "PASS" in results:
        status, reason = "CONFLICTED", "current evidence both supports and refutes this claim"
    elif "FAIL" in results:
        status, reason = "FAILED", "current evidence refutes this claim"
    elif "BLOCKED" in results:
        status, reason = "BLOCKED", "a required verifier could not run to a verdict"
    elif "UNKNOWN" in results:
        status, reason = "UNKNOWN", "a required verifier returned no verdict"
    elif not required:
        status, reason = (
            "UNKNOWN",
            obligation.get("plan", {}).get("route", "no verifier is selected for this claim"),
        )
    elif required <= proven:
        status, reason = "VERIFIED", "every required verifier has current passing evidence"
    elif stale:
        # Naming staleness before anything else says which of the two things happened:
        # this claim was settled once and its inputs moved, rather than never settled.
        status, reason = "STALE", "the evidence for this claim no longer matches current inputs"
    else:
        status, reason = "UNRESOLVED", "required evidence has not been produced yet"
    if human and status == "UNRESOLVED":
        status, reason = "HUMAN_REQUIRED", "no automated verifier can settle this claim"
    return {
        "obligation_id": obligation["id"],
        "status": status,
        "reason": reason,
        "current": [e["id"] for e in current],
        "stale": [e["id"] for e in stale],
        "superseded": [e["id"] for e in related if e not in matched],
        "missing_verifiers": sorted(required - proven),
        "binding_digest": digest(scoped),
    }


def resolve_all(plane: Any, task: dict[str, Any]) -> list[dict[str, Any]]:
    from ..verification import binding as task_level_binding

    obligations = obligations_for(plane, task["id"])
    if not obligations:
        return []
    records = [e for e in plane.store.list("evidence") if e["task_id"] == task["id"]]
    # The task-wide binding fingerprints the whole declared scope, so it is the expensive
    # part of resolution. It is only needed for a record that carries no binding of its
    # own; when every record does, an empty one is passed and can only read as stale.
    legacy = any(
        o["id"] not in (e.get("obligation_bindings") or {}) for e in records for o in obligations
    )
    conservative: dict[str, Any] = {}
    if legacy:
        try:
            conservative = task_level_binding(plane, task)
        except (OSError, RuntimeError):
            conservative = {}
    return [
        resolve(plane, task, o, evidence=records, task_binding=conservative) for o in obligations
    ]


def obligations_for(plane: Any, task_id: str) -> list[dict[str, Any]]:
    """A reverted obligation stays readable for audit but no longer governs anything."""
    return [
        o
        for o in plane.store.list("obligation")
        if o["task_id"] == task_id and not o.get("reverted")
    ]


def counts(states: list[str]) -> dict[str, int]:
    return {state: states.count(state) for state in sorted(set(states))}


def debt(plane: Any, task: dict[str, Any]) -> dict[str, Any]:
    """Proof debt: mandatory, enforced obligations that current evidence does not close."""
    obligations = {o["id"]: o for o in obligations_for(plane, task["id"])}
    resolutions = resolve_all(plane, task)
    required = [r for r in resolutions if _counts(obligations[r["obligation_id"]])]
    outstanding = [r for r in required if r["status"] not in RESOLVED]
    return {
        "task_id": task["id"],
        "obligations": len(obligations),
        "required": len(required),
        "verified": sum(r["status"] == "VERIFIED" for r in required),
        "waived": sum(r["status"] == "WAIVED" for r in required),
        "counts": counts([r["status"] for r in resolutions]),
        "required_counts": counts([r["status"] for r in required]),
        "proof_debt": len(outstanding),
        "outstanding": [
            {
                **r,
                "claim": obligations[r["obligation_id"]]["claim"],
                "criticality": obligations[r["obligation_id"]]["criticality"],
            }
            for r in outstanding
        ],
        "resolutions": resolutions,
    }


def _counts(obligation: dict[str, Any]) -> bool:
    return bool(obligation["mandatory"] and obligation["enforced"])
