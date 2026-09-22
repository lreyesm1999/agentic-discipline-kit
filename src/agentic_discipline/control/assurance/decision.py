"""Whether the work may advance. Evidence decides this, not the agent's confidence."""

from __future__ import annotations

from typing import Any

from .impact import in_scope

DECISIONS = (
    "COMPLETE",
    "BLOCK",
    "ESCALATE",
    "HUMAN_REQUIRED",
    "REPAIR",
    "EXPAND_VERIFICATION",
    "CONTINUE",
)


def repairable(plane: Any, task: dict[str, Any], outstanding: list[dict[str, Any]]) -> bool:
    """A failure is repairable when the contract still authorizes another attempt here."""
    if task["attempts"] > task["budget"]["max_retries"]:
        return False
    protected = plane.policy()["protected_paths"]
    obligations = {o["id"]: o for o in plane.store.list("obligation")}
    for item in outstanding:
        paths = obligations[item["obligation_id"]]["affected_paths"]
        if any(not in_scope(p, task["scope"]) for p in paths):
            return False
        if any(in_scope(p, protected) for p in paths):
            return False
    return True


def decide(plane: Any, task: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    obligations = {o["id"]: o for o in plane.store.list("obligation") if o["task_id"] == task["id"]}
    outstanding = report["outstanding"]
    by_status: dict[str, list[dict[str, Any]]] = {}
    for item in outstanding:
        by_status.setdefault(item["status"], []).append(item)
    severe = [
        item
        for item in outstanding
        if obligations[item["obligation_id"]]["criticality"] in {"HIGH", "CRITICAL"}
    ]
    if not obligations:
        decision, reasons = "CONTINUE", ["no assurance plan has been compiled for this task"]
    elif not outstanding:
        decision, reasons = (
            "COMPLETE",
            ["every mandatory obligation is resolved by current evidence"],
        )
    elif by_status.get("CONFLICTED"):
        decision, reasons = (
            "BLOCK",
            [
                f"conflicting evidence on {i['obligation_id']}: {i['claim']}"
                for i in by_status["CONFLICTED"]
            ],
        )
    elif by_status.get("FAILED"):
        failures = by_status["FAILED"]
        if repairable(plane, task, failures):
            decision, reasons = (
                "REPAIR",
                [
                    f"{i['obligation_id']} failed inside the task contract: {i['claim']}"
                    for i in failures
                ],
            )
        else:
            decision, reasons = (
                "BLOCK",
                [
                    f"{i['obligation_id']} failed outside what this task may repair"
                    for i in failures
                ],
            )
    elif by_status.get("BLOCKED") or (by_status.get("UNKNOWN") and severe):
        decision, reasons = (
            "ESCALATE",
            [
                f"{i['obligation_id']} is {i['status']}: {i['reason']}"
                for i in by_status.get("BLOCKED", []) + by_status.get("UNKNOWN", [])
            ],
        )
    elif by_status.get("HUMAN_REQUIRED"):
        decision, reasons = (
            "HUMAN_REQUIRED",
            [
                f"{i['obligation_id']} needs human judgment: {i['claim']}"
                for i in by_status["HUMAN_REQUIRED"]
            ],
        )
    elif any(
        obligations[i["obligation_id"]]["required_verifiers"]
        for i in outstanding
        if i["status"] in {"STALE", "UNRESOLVED"}
    ):
        decision, reasons = (
            "EXPAND_VERIFICATION",
            [f"{i['obligation_id']} needs a verifier run: {i['reason']}" for i in outstanding],
        )
    else:
        decision, reasons = (
            "ESCALATE",
            [
                f"{i['obligation_id']} cannot be resolved by any declared verifier"
                for i in outstanding
            ],
        )
    return {
        "task_id": task["id"],
        "decision": decision,
        "reasons": reasons,
        "proof_debt": report["proof_debt"],
        "risk": task["risk"],
        "required_counts": report["required_counts"],
        "completion_allowed": decision == "COMPLETE",
        "next_actions": _next_actions(outstanding, obligations),
    }


def _next_actions(
    outstanding: list[dict[str, Any]], obligations: dict[str, dict[str, Any]]
) -> list[str]:
    actions = []
    for item in sorted(outstanding, key=lambda i: (i["status"], i["obligation_id"])):
        obligation = obligations[item["obligation_id"]]
        if item["status"] in {"STALE", "UNRESOLVED"}:
            actions.append(f"Run the verifier for {item['obligation_id']} and record evidence.")
        elif item["status"] == "FAILED":
            actions.append(f"Resolve the failure behind {item['obligation_id']}.")
        elif item["status"] == "CONFLICTED":
            actions.append(
                f"Reconcile the contradictory evidence on {item['obligation_id']} before continuing."
            )
        elif item["status"] == "HUMAN_REQUIRED":
            actions.append(f"Ask a human to settle {item['obligation_id']}: {obligation['claim']}")
        else:
            actions.append(
                f"Declare a verifier that can supply "
                f"{', '.join(obligation['acceptable_proof_capabilities']) or 'this capability'} "
                f"for {item['obligation_id']}, or record an owner waiver."
            )
    return actions


def mandatory_debt(plane: Any, task: dict[str, Any]) -> list[dict[str, Any]]:
    """The single question completion asks: is any mandatory claim still unresolved?"""
    from .resolver import debt, obligations_for

    if not obligations_for(plane, task["id"]):
        return []
    # `outstanding` already excludes what is resolved; it is the debt, not a view of it.
    outstanding: list[dict[str, Any]] = debt(plane, task)["outstanding"]
    return outstanding
