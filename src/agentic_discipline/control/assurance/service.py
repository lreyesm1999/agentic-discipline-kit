"""One application layer for assurance, used by the CLI, the API, MCP and the console.

A persisted obligation carries only the state an owner action sets: UNRESOLVED, or
WAIVED with its audited waiver. Everything the engine reports is recomputed from
current evidence, so no cached verdict can outlive the facts behind it.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ...evidence import sha256_file
from ..contracts import ControlError, encode, require, uid
from ..discovery import area
from .compiler import compile_obligations
from .decision import decide
from .model import (
    RESOLVED,
    contraction,
    depth,
    is_obligation,
    monotonic,
    obligation_contract,
    plan_digest,
)
from .planner import plan as plan_routes
from .registry import Registry, descriptor_contract, normalized
from .resolver import debt, obligation_binding, obligations_for, resolve, resolve_all


def enabled(plane: Any) -> bool:
    """Assurance governs a project only once its state has been migrated explicitly."""
    return bool(plane.store.schema_version >= 2)


def require_enabled(plane: Any) -> None:
    require(
        enabled(plane),
        "ASSURANCE_DISABLED",
        "Run 'agentic assurance migrate' to enable the assurance engine for this project",
    )


def registry_for(plane: Any) -> Registry:
    return Registry(plane.store.list("verifier_capability"))


def registry(plane: Any) -> dict[str, Any]:
    known = registry_for(plane)
    return {
        "verifiers": known.describe(),
        "deterministic_capabilities": sorted(known.deterministic_capabilities()),
        "note": "a task contract supplies the argv; this describes what each kind proves",
    }


def register_verifier(plane: Any, descriptor: dict[str, Any]) -> dict[str, Any]:
    require_enabled(plane)
    descriptor_contract(descriptor)
    entry = normalized(descriptor)
    existing = [r for r in plane.store.list("verifier_capability") if r["id"] == entry["id"]]
    with plane.store.transaction():
        record: dict[str, Any] = plane.store.put(
            "verifier_capability",
            entry,
            expected=existing[0]["version"] if existing else None,
            actor="local-owner",
        )
    return record


def compile_plan(plane: Any, task_id: str, *, phase: str) -> dict[str, Any]:
    """Compile, then merge into stored obligations without ever asking for less."""
    require_enabled(plane)
    task = plane.store.get(task_id, "task")
    registry = registry_for(plane)
    existing = {o["id"]: o for o in obligations_for(plane, task_id)}
    floors = {i: o["floor"] for i, o in existing.items() if o.get("floor")}
    compiled = compile_obligations(plane, task, registry, phase=phase)
    candidates = plan_routes(task, compiled["obligations"], registry, floors=floors)
    now = time.time()
    added, widened, refused = [], [], []
    with plane.store.transaction():
        for candidate in candidates:
            previous = existing.get(candidate["id"])
            if previous is None:
                # The depth is recorded from the start, so a later merge has nothing to add
                # and an identical recompile writes no revision.
                payload = {
                    **candidate,
                    "floor": depth(candidate),
                    "created_at": now,
                    "updated_at": now,
                    "waiver_id": None,
                }
                obligation_contract(payload)
                plane.store.put("obligation", payload)
                added.append(candidate["id"])
                continue
            findings = contraction(previous, candidate)
            if findings:
                refused.append({"obligation_id": previous["id"], "refused": findings})
            merged = monotonic(previous, candidate)
            # The merge starts from the stored record, so any difference is a real change.
            if merged != previous:
                merged["updated_at"] = now
                obligation_contract(merged)
                plane.store.put("obligation", merged, expected=previous["version"])
                widened.append(previous["id"])
        stored = {o["id"]: o for o in obligations_for(plane, task_id)}
        retained = sorted(set(stored) - {c["id"] for c in candidates})
        record = plane.store.put(
            "assurance_plan",
            {
                "task_id": task_id,
                "phase": phase,
                "obligations": sorted(stored),
                "added": sorted(added),
                "widened": sorted(widened),
                "retained": retained,
                "refused_contractions": refused,
                "observed_paths": compiled["observed_paths"],
                "signals": compiled["signals"],
                "impact": compiled["impact"],
                "plan_digest": plan_digest(list(stored.values())),
                "created_at": now,
            },
        )
        plane.store.event(
            "local",
            "assurance.compile",
            {
                "task_id": task_id,
                "phase": phase,
                "added": sorted(added),
                "widened": sorted(widened),
                "retained": retained,
                "refused_contractions": refused,
            },
        )
    return {
        **record,
        "expansion": {
            "added": sorted(added),
            "widened": sorted(widened),
            "retained": retained,
            "reason": "obligations only widen; a recorded obligation is never dropped by a recompile",
        },
    }


def reconcile(plane: Any, task_id: str) -> dict[str, Any]:
    return compile_plan(plane, task_id, phase="RECONCILED")


# A route that produced no verdict, or none at all, is the only reason to go deeper.
# A plain failure means repair, and a stale result means rerun; neither escalates.
ESCALATES = {"UNKNOWN", "BLOCKED"}


def escalate(plane: Any, task_id: str, outstanding: list[dict[str, Any]]) -> list[str]:
    """Raise the required depth for claims the current route could not settle."""
    raised = []
    stored = {o["id"]: o for o in obligations_for(plane, task_id)}
    with plane.store.transaction():
        for item in outstanding:
            obligation = stored[item["obligation_id"]]
            if item["status"] not in ESCALATES or obligation["derivation"] == "CONTRACT":
                continue
            current = depth(obligation)
            if current >= 4:
                continue
            plane.store.put(
                "obligation",
                {**obligation, "floor": current + 1, "updated_at": time.time()},
                expected=obligation["version"],
            )
            raised.append(obligation["id"])
        if raised:
            plane.store.event(
                "local", "assurance.escalate", {"task_id": task_id, "obligations": raised}
            )
    return raised


def pending_specs(plane: Any, task_id: str, outstanding: list[dict[str, Any]]) -> list[str]:
    stored = {o["id"]: o for o in obligations_for(plane, task_id)}
    return sorted(
        {
            spec
            for item in outstanding
            if item["status"] in {"UNRESOLVED", "STALE", "FAILED"}
            for spec in stored[item["obligation_id"]]["required_verifiers"]
            if not spec.startswith("human:")
        }
    )


def verify(plane: Any, task_id: str, session: str, *, rounds: int = 2) -> dict[str, Any]:
    """Focused verification first; expand only when the evidence says it is necessary."""
    require_enabled(plane)
    from ..verification import verify as run_verifiers

    executions: list[dict[str, Any]] = []
    escalations: list[str] = []
    plans = [reconcile(plane, task_id)]
    # `reconcile` has read this identifier as a task already; these are re-reads.
    task = plane.store.get(task_id)
    report = debt(plane, task)
    for _ in range(max(1, rounds)):
        specs = pending_specs(plane, task_id, report["outstanding"])
        if specs:
            executions.append(run_verifiers(plane, task_id, session, specs=specs))
            task = plane.store.get(task_id)
            report = debt(plane, task)
        if not report["outstanding"]:
            break
        raised = escalate(plane, task_id, report["outstanding"])
        if not raised:
            break
        escalations.extend(raised)
        plans.append(reconcile(plane, task_id))
        task = plane.store.get(task_id)
        report = debt(plane, task)
        if not pending_specs(plane, task_id, report["outstanding"]):
            break
    decision = decide(plane, task, report)
    return {
        "task_id": task_id,
        "status": "PASS" if decision["completion_allowed"] else "FAIL",
        "decision": decision,
        "debt": report,
        "executions": executions,
        "escalated": escalations,
        "plan": plans[-1],
    }


def task_report(plane: Any, task: dict[str, Any]) -> dict[str, Any]:
    obligations = {o["id"]: o for o in obligations_for(plane, task["id"])}
    report = debt(plane, task)
    return {
        "task_id": task["id"],
        "objective": task["objective"],
        "state": task["state"],
        "risk": task["risk"],
        "obligations": [
            {
                "id": o["id"],
                "claim": o["claim"],
                "criticality": o["criticality"],
                "mandatory": o["mandatory"],
                "enforced": o["enforced"],
                "derivation": o["derivation"],
                "level": o["level"],
                "capabilities": o["acceptable_proof_capabilities"],
                "status": next(
                    r["status"] for r in report["resolutions"] if r["obligation_id"] == o["id"]
                ),
            }
            for o in (obligations[k] for k in sorted(obligations))
        ],
        "required": report["required"],
        "counts": report["required_counts"],
        "proof_debt": report["proof_debt"],
        "decision": decide(plane, task, report),
    }


def status(plane: Any, task_id: str | None = None) -> dict[str, Any]:
    require_enabled(plane)
    tasks = (
        [plane.store.get(task_id, "task")]
        if task_id
        else [
            t
            for t in plane.store.list("task")
            if t["state"] not in {"CANCELLED", "SUPERSEDED"} and obligations_for(plane, t["id"])
        ]
    )
    reports = [task_report(plane, task) for task in tasks]
    return {
        "tasks": reports,
        "totals": {
            "required": sum(r["required"] for r in reports),
            "proof_debt": sum(r["proof_debt"] for r in reports),
            "blocked_completion": [r["task_id"] for r in reports if r["proof_debt"]],
        },
        "meaning": "required obligations are mandatory and confirmed by the actual change",
    }


def debt_report(plane: Any, task_id: str | None = None) -> dict[str, Any]:
    require_enabled(plane)
    tasks = (
        [plane.store.get(task_id, "task")]
        if task_id
        else [t for t in plane.store.list("task") if obligations_for(plane, t["id"])]
    )
    reports = [debt(plane, task) for task in tasks]
    by_requirement: dict[str, int] = {}
    by_area: dict[str, int] = {}
    stale: list[str] = []
    stored = {o["id"]: o for o in plane.store.list("obligation")}
    for report in reports:
        for item in report["outstanding"]:
            obligation = stored[item["obligation_id"]]
            for requirement in obligation["origin"]["requirement_ids"]:
                by_requirement[requirement] = by_requirement.get(requirement, 0) + 1
            # The same areas discovery already classifies, so debt can be read by the part
            # of the repository it sits in rather than only by task.
            for name in {area(Path(p)) for p in obligation["affected_paths"]}:
                by_area[name] = by_area.get(name, 0) + 1
        for resolution in report["resolutions"]:
            stale.extend(resolution["stale"])
    return {
        "tasks": reports,
        "proof_debt": sum(r["proof_debt"] for r in reports),
        "by_task": {r["task_id"]: r["proof_debt"] for r in reports},
        "by_requirement": by_requirement,
        "by_criticality": _by_criticality(reports, stored),
        "by_area": by_area,
        # Which evidence stopped speaking for a claim, which is the question a change that
        # invalidated something leaves behind.
        "stale_evidence": sorted(set(stale)),
    }


def _by_criticality(
    reports: list[dict[str, Any]], stored: dict[str, dict[str, Any]]
) -> dict[str, int]:
    result: dict[str, int] = {}
    for report in reports:
        for item in report["outstanding"]:
            level = stored[item["obligation_id"]]["criticality"]
            result[level] = result.get(level, 0) + 1
    return result


def explain(plane: Any, identifier: str) -> dict[str, Any]:
    """Explain one claim, or a whole task when a task is what was asked about."""
    require_enabled(plane)
    if not is_obligation(identifier):
        return explain_task(plane, identifier)
    return explain_obligation(plane, identifier)


def explain_task(plane: Any, task_id: str) -> dict[str, Any]:
    """Why this task can or cannot complete, and exactly what would change that."""
    task = plane.store.get(task_id, "task")
    obligations = {o["id"]: o for o in obligations_for(plane, task_id)}
    require(obligations, "NO_ASSURANCE_PLAN", "Compile an assurance plan for this task first")
    report = debt(plane, task)
    decision = decide(plane, task, report)
    return {
        "task_id": task_id,
        "objective": task["objective"],
        "state": task["state"],
        "can_complete": decision["completion_allowed"],
        "headline": f"{task_id} "
        + ("is ready to complete." if decision["completion_allowed"] else "cannot complete."),
        "required": report["required"],
        "counts": report["required_counts"],
        "proof_debt": report["proof_debt"],
        "decision": decision["decision"],
        "outstanding": [
            {
                "obligation_id": item["obligation_id"],
                "status": item["status"],
                "claim": item["claim"],
                "criticality": item["criticality"],
                "reason": item["reason"],
                "current_evidence": item["current"],
                "stale_evidence": item["stale"],
                "missing_verifiers": item["missing_verifiers"],
                "origin": obligations[item["obligation_id"]]["origin"]["generated_reason"],
            }
            for item in report["outstanding"]
        ],
        "required_next_actions": decision["next_actions"],
    }


def explain_obligation(plane: Any, obligation_id: str) -> dict[str, Any]:
    obligation = plane.store.get(obligation_id, "obligation")
    task = plane.store.get(obligation["task_id"], "task")
    records = [e for e in plane.store.list("evidence") if e["task_id"] == task["id"]]
    resolution = resolve(plane, task, obligation)
    lookup = {e["id"]: e for e in records}
    requirements = [plane.store.get(i, "entity") for i in obligation["origin"]["requirement_ids"]]
    return {
        "obligation": obligation,
        "task_id": task["id"],
        "claim": obligation["claim"],
        "origin": {
            **obligation["origin"],
            "requirements": [
                {"id": r["id"], "name": r["name"], "authority": r["authority"]}
                for r in requirements
            ],
            "acceptance": [task["acceptance"][i] for i in obligation["origin"]["acceptance_ids"]],
        },
        "required_because": obligation["origin"]["generated_reason"],
        "affected_paths": obligation["affected_paths"],
        "affected_symbols": obligation["affected_symbols"],
        "plan": obligation["plan"],
        "status": resolution["status"],
        "reason": resolution["reason"],
        "evidence": [
            {
                "id": identifier,
                "kind": lookup[identifier]["kind"],
                "result": lookup[identifier]["result"],
                "evidence_class": lookup[identifier].get("evidence_class", "MEASURED"),
                "command": lookup[identifier]["command"],
                "exit_code": lookup[identifier]["exit_code"],
                "currency": currency,
            }
            for currency, group in (
                ("CURRENT", resolution["current"]),
                ("STALE", resolution["stale"]),
                ("SUPERSEDED", resolution["superseded"]),
            )
            for identifier in group
        ],
        "missing_verifiers": resolution["missing_verifiers"],
        "waiver": plane.store.get(obligation["waiver_id"], "waiver")
        if obligation.get("waiver_id")
        else None,
        "human_request": human_request(plane, task, obligation, resolution)
        if resolution["status"] == "HUMAN_REQUIRED"
        else None,
    }


def human_request(
    plane: Any, task: dict[str, Any], obligation: dict[str, Any], resolution: dict[str, Any]
) -> dict[str, Any]:
    """A concrete request: the claim, what to look at, what already passed, what is left."""
    # What the automated checks on this change already settled, so the human is asked
    # only for the part no verifier reached.
    passed = sorted(
        {
            e["kind"]
            for e in plane.store.list("evidence")
            if e["task_id"] == task["id"] and e["result"] == "PASS" and e["kind"] != "human"
        }
    )
    return {
        "obligation_id": obligation["id"],
        "claim": obligation["claim"],
        "inspect": obligation["affected_paths"],
        "reference": obligation["origin"]["architecture_ids"],
        "automatic_checks_passed": passed,
        "remaining_judgment": obligation["origin"]["generated_reason"],
        "why_no_verifier": obligation["plan"]["route"],
        "resolve_with": f"agentic assurance resolve {obligation['id']} --decision <text>",
        "current_status": resolution["status"],
    }


def waive(plane: Any, obligation_id: str, reason: str, authorization: str) -> dict[str, Any]:
    """The only sanctioned contraction, and it cannot hide a current failure."""
    require_enabled(plane)
    require(
        bool(reason.strip()) and bool(authorization.strip()),
        "DECISION_REQUIRED",
        "A waiver needs a reason and the authority that granted it",
    )
    obligation = plane.store.get(obligation_id, "obligation")
    task = plane.store.get(obligation["task_id"], "task")
    resolution = resolve(plane, task, obligation)
    require(
        resolution["status"] not in {"FAILED", "CONFLICTED"},
        "EVIDENCE_REFUTES_CLAIM",
        "Current evidence refutes this claim; a waiver cannot hide it",
    )
    with plane.store.transaction():
        record = plane.store.put(
            "waiver",
            {
                "obligation_id": obligation_id,
                "task_id": task["id"],
                "claim": obligation["claim"],
                "criticality": obligation["criticality"],
                "reason": reason,
                "authorization": authorization,
                "status_when_waived": resolution["status"],
                "created_at": time.time(),
            },
            actor="local-owner",
        )
        updated = plane.store.put(
            "obligation",
            {
                **obligation,
                "status": "WAIVED",
                "waiver_id": record["id"],
                "updated_at": time.time(),
            },
            expected=obligation["version"],
            actor="local-owner",
        )
        plane.store.event(
            "local-owner",
            "assurance.waive",
            {
                "obligation_id": obligation_id,
                "criticality": obligation["criticality"],
                "reason": reason,
                "authorization": authorization,
            },
        )
    return {"obligation": updated, "waiver": record}


def resolve_human(
    plane: Any, obligation_id: str, decision: str, accepted: bool = True
) -> dict[str, Any]:
    """Record a human verdict as evidence, bound to the artefacts it was given."""
    require_enabled(plane)
    require(bool(decision.strip()), "DECISION_REQUIRED", "Record what the human decided")
    obligation = plane.store.get(obligation_id, "obligation")
    task = plane.store.get(obligation["task_id"], "task")
    require(
        bool(obligation["plan"].get("human_required")),
        "NOT_HUMAN_REQUIRED",
        "This obligation has an automated route; run it instead",
    )
    from ..verification import binding as task_level_binding

    identifier = uid("EVD")
    artifact = plane.directory / "evidence" / (identifier + ".json")
    require(
        not artifact.parent.is_symlink(), "INVALID_PATH", "Evidence directory must not be a symlink"
    )
    artifact.parent.mkdir(exist_ok=True, mode=0o700)
    payload = {
        "tool": "human",
        "obligation_id": obligation_id,
        "claim": obligation["claim"],
        "decision": decision,
        "accepted": accepted,
        "inspected": obligation["affected_paths"],
        "result": "PASS" if accepted else "FAIL",
        "exit_code": 0 if accepted else 1,
        "recorded_at": time.time(),
    }
    artifact.write_bytes(encode(payload).encode("utf-8"))
    artifact.chmod(0o600)
    scoped = obligation_binding(plane, task, obligation)
    with plane.store.transaction():
        record = plane.store.put(
            "evidence",
            {
                "id": identifier,
                "task_id": task["id"],
                "kind": "human",
                "verifier": f"human:{obligation_id}",
                "acceptance": obligation["origin"]["acceptance_ids"],
                "run_id": identifier,
                "result": "PASS" if accepted else "FAIL",
                "exit_code": 0 if accepted else 1,
                "command": [],
                "evidence_class": "HUMAN",
                "judgment": "ACCEPTED" if accepted else "REJECTED",
                "binding": task_level_binding(plane, task),
                "obligation_ids": [obligation_id],
                "obligation_bindings": {obligation_id: scoped},
                "knowledge_version": plane.store.knowledge_version,
                "artifact_hash": sha256_file(artifact),
                "artifact_ref": f".agentic/control/evidence/{identifier}.json",
                "started_at": payload["recorded_at"],
                "finished_at": payload["recorded_at"],
                "run_consistent": True,
                "stale": False,
            },
            actor="local-owner",
        )
        plane.store.put(
            "decision",
            {
                "obligation_id": obligation_id,
                "task_id": task["id"],
                "question": obligation["claim"],
                "decision": decision,
                "state": "DECIDED",
                "authority": "human",
            },
            actor="local-owner",
        )
    return {"evidence": record, "obligation": plane.store.get(obligation_id)}


def integrity(plane: Any) -> dict[str, Any]:
    """Deterministic invariants an agent must not be able to talk its way around."""
    if not enabled(plane):
        return {"status": "NOT_APPLICABLE", "findings": [], "obligations": 0}
    findings: list[dict[str, Any]] = []
    obligations = plane.store.list("obligation")
    waivers = {w["obligation_id"]: w for w in plane.store.list("waiver")}
    for obligation in obligations:
        if obligation["status"] == "WAIVED":
            waiver = waivers.get(obligation["id"])
            if not waiver or not str(waiver.get("reason", "")).strip():
                findings.append(
                    {
                        "obligation_id": obligation["id"],
                        "finding": "waived without a recorded waiver",
                    }
                )
        elif obligation["status"] != "UNRESOLVED":
            findings.append(
                {
                    "obligation_id": obligation["id"],
                    "finding": f"persisted status {obligation['status']} is not an owner state",
                }
            )
    recorded = {o["id"] for o in obligations}
    for plan in plane.store.list("assurance_plan"):
        missing = sorted(set(plan["obligations"]) - recorded)
        if missing:
            findings.append(
                {
                    "task_id": plan["task_id"],
                    "finding": "obligations recorded in an assurance plan are gone from the store",
                    "obligations": missing,
                }
            )
    for task in plane.store.list("task"):
        if not obligations_for(plane, task["id"]):
            continue
        try:
            outstanding = [r for r in resolve_all(plane, task) if r["status"] not in RESOLVED]
        except (ControlError, OSError):
            continue
        mandatory = {
            o["id"] for o in obligations_for(plane, task["id"]) if o["mandatory"] and o["enforced"]
        }
        open_mandatory = [r for r in outstanding if r["obligation_id"] in mandatory]
        if task["state"] == "COMPLETED" and open_mandatory:
            findings.append(
                {
                    "task_id": task["id"],
                    "finding": "completed while holding mandatory proof debt",
                    "obligations": [r["obligation_id"] for r in open_mandatory],
                }
            )
    for evidence in plane.store.list("evidence"):
        declared = evidence.get("evidence_class")
        if declared == "DETERMINISTIC" and evidence.get("judgment"):
            findings.append(
                {
                    "evidence_id": evidence["id"],
                    "finding": "judgment evidence declared as deterministic",
                }
            )
        if evidence.get("obligation_ids") and not evidence.get("run_id"):
            findings.append(
                {
                    "evidence_id": evidence["id"],
                    "finding": "evidence does not reference the execution that created it",
                }
            )
    return {
        "status": "PASS" if not findings else "FAIL",
        "findings": findings,
        "obligations": len(obligations),
        "waivers": len(waivers),
        "checked": [
            "obligation status is an owner state",
            "no obligation a plan recorded has disappeared",
            "every waiver records a reason and its authority",
            "no completed task holds mandatory proof debt",
            "judgment evidence never claims a deterministic class",
            "evidence references the run that produced it",
        ],
    }


def plan_view(plane: Any, task_id: str) -> dict[str, Any]:
    require_enabled(plane)
    plans = [p for p in plane.store.list("assurance_plan") if p["task_id"] == task_id]
    require(plans, "NO_ASSURANCE_PLAN", "Compile an assurance plan for this task first")
    latest = max(plans, key=lambda p: p["created_at"])
    initial = min(plans, key=lambda p: p["created_at"])
    obligations = {o["id"]: o for o in obligations_for(plane, task_id)}
    return {
        "task_id": task_id,
        "initial": {
            "phase": initial["phase"],
            "obligations": len(initial["obligations"]),
            "plan_digest": initial["plan_digest"],
        },
        "current": {
            "phase": latest["phase"],
            "obligations": len(latest["obligations"]),
            "plan_digest": latest["plan_digest"],
            "signals": latest["signals"],
            "observed_paths": latest["observed_paths"],
            "impact": latest["impact"],
        },
        "expanded_by": sorted(set(latest["obligations"]) - set(initial["obligations"])),
        "revisions": len(plans),
        "routes": {
            i: {
                "claim": o["claim"],
                "level": o["level"],
                "route": o["plan"]["route"],
                "verifiers": o["required_verifiers"],
            }
            for i, o in sorted(obligations.items())
        },
    }
