"""Proof obligations: the claims a change must keep true, with provenance and state."""

from __future__ import annotations

import hashlib
from typing import Any

from ..contracts import digest, require, safe_data

# A claim is resolved only by current evidence or an audited waiver. Everything else,
# including UNKNOWN, is proof debt.
RESOLVED = {"VERIFIED", "WAIVED"}
STATUSES = {
    "UNRESOLVED",
    "VERIFYING",
    "VERIFIED",
    "FAILED",
    "UNKNOWN",
    "BLOCKED",
    "CONFLICTED",
    "STALE",
    "WAIVED",
    "HUMAN_REQUIRED",
}
CRITICALITY = ("LOW", "STANDARD", "HIGH", "CRITICAL")
EVIDENCE_CLASSES = ("DETERMINISTIC", "MEASURED", "AGENT_JUDGMENT", "HUMAN")
COSTS = ("low", "medium", "high", "manual")
DERIVATIONS = {"CONTRACT", "POLICY", "IMPACT"}
PHASES = {"INITIAL", "RECONCILED"}
# Progressive assurance: existing evidence, focused deterministic, broader/property,
# adversarial/falsification, human. The numbers order escalation; they are not a score.
LEVELS = (0, 1, 2, 3, 4)
CAPABILITIES = {
    "unit",
    "integration",
    "acceptance",
    "behavioral",
    "regression",
    "property",
    "invariant",
    "falsification",
    "test_strength",
    "contract_compatibility",
    "schema_compatibility",
    "migration_safety",
    "data_preservation",
    "historical_stability",
    "authorization_boundary",
    "security",
    "architecture",
    "static_analysis",
    "coverage",
    "reference_comparison",
    "qualitative_reference_comparison",
    "falsification_review",
    "human_judgment",
}
# Capabilities no automated verifier can supply on its own.
HUMAN_ONLY = {"human_judgment"}
ORIGIN_KEYS = (
    "requirement_ids",
    "acceptance_ids",
    "policy_ids",
    "architecture_ids",
    "generated_reason",
)
FIELDS = (
    "task_id",
    "claim",
    "origin",
    "derivation",
    "criticality",
    "mandatory",
    "status",
    "phase",
    "enforced",
    "acceptable_proof_capabilities",
    "required_verifiers",
    "affected_paths",
    "affected_symbols",
    "dependencies",
)
# A recompilation may widen an obligation. These carry identity, authority or history
# and change only through their own audited operations.
FROZEN = {
    "id",
    "version",
    "task_id",
    "claim",
    "status",
    "waiver_id",
    "created_at",
    "human_request",
}


# An obligation identifier is recognisable on sight, so one command can take either an
# obligation or the task it belongs to without having to guess at the store.
PREFIX = "PO-"


def obligation_id(task_id: str, origin_key: str) -> str:
    """Deterministic identity, so recompiling a plan updates rather than duplicates."""
    return PREFIX + hashlib.sha256(f"{task_id}\x00{origin_key}".encode()).hexdigest()[:16]


def is_obligation(identifier: str) -> bool:
    return identifier.startswith(PREFIX)


def stronger(left: str, right: str) -> str:
    return left if CRITICALITY.index(left) >= CRITICALITY.index(right) else right


def obligation_contract(data: dict[str, Any]) -> None:
    missing = sorted(set(FIELDS) - data.keys())
    require(not missing, "INVALID_OBLIGATION", f"Missing obligation fields: {missing}")
    for key in ("task_id", "claim"):
        require(
            isinstance(data[key], str) and bool(data[key].strip()),
            "INVALID_OBLIGATION",
            f"{key} must be nonempty text",
        )
    require(
        isinstance(data["criticality"], str) and data["criticality"] in CRITICALITY,
        "INVALID_OBLIGATION",
        "Unknown criticality",
    )
    require(
        isinstance(data["status"], str) and data["status"] in STATUSES,
        "INVALID_OBLIGATION",
        "Unknown obligation status",
    )
    require(
        isinstance(data["derivation"], str) and data["derivation"] in DERIVATIONS,
        "INVALID_OBLIGATION",
        "Unknown derivation",
    )
    require(
        isinstance(data["phase"], str) and data["phase"] in PHASES,
        "INVALID_OBLIGATION",
        "Unknown compilation phase",
    )
    for key in ("mandatory", "enforced"):
        require(type(data[key]) is bool, "INVALID_OBLIGATION", f"{key} must be a boolean")
    for key in ("required_verifiers", "affected_paths", "affected_symbols", "dependencies"):
        require(
            isinstance(data[key], list) and all(isinstance(x, str) and x for x in data[key]),
            "INVALID_OBLIGATION",
            f"Invalid list: {key}",
        )
    capabilities = data["acceptable_proof_capabilities"]
    require(
        isinstance(capabilities, list) and set(capabilities) <= CAPABILITIES,
        "INVALID_OBLIGATION",
        "Unknown proof capability",
    )
    origin = data["origin"]
    require(
        isinstance(origin, dict) and set(ORIGIN_KEYS) <= origin.keys(),
        "INVALID_OBLIGATION",
        "Obligation lacks provenance",
    )
    require(
        isinstance(origin["generated_reason"], str) and bool(origin["generated_reason"].strip()),
        "INVALID_OBLIGATION",
        "Provenance needs the reason this obligation exists",
    )
    require(
        isinstance(origin["acceptance_ids"], list)
        and all(type(i) is int and i >= 0 for i in origin["acceptance_ids"]),
        "INVALID_OBLIGATION",
        "Acceptance provenance must be criterion indexes",
    )
    for key in ("requirement_ids", "policy_ids", "architecture_ids"):
        require(
            isinstance(origin[key], list) and all(isinstance(x, str) and x for x in origin[key]),
            "INVALID_OBLIGATION",
            f"Invalid provenance list: {key}",
        )
    safe_data(data)


def monotonic(previous: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Merge a recompiled obligation into a stored one without ever weakening it."""
    return {
        **previous,
        **{k: v for k, v in candidate.items() if k not in FROZEN},
        "mandatory": previous["mandatory"] or candidate["mandatory"],
        "criticality": stronger(previous["criticality"], candidate["criticality"]),
        "enforced": previous["enforced"] or candidate["enforced"],
        "affected_paths": sorted(
            set(previous["affected_paths"]) | set(candidate["affected_paths"])
        ),
        "affected_symbols": sorted(
            set(previous["affected_symbols"]) | set(candidate["affected_symbols"])
        ),
        "acceptable_proof_capabilities": sorted(
            set(previous["acceptable_proof_capabilities"])
            | set(candidate["acceptable_proof_capabilities"])
        ),
        # `required_verifiers` is the current route, not an accumulated set: escalating
        # away from a verifier that produced no verdict replaces it. Depth is what may
        # not fall, and `floor` keeps that monotonic.
        "floor": max(depth(previous), depth(candidate)),
        "dependencies": sorted(set(previous["dependencies"]) | set(candidate["dependencies"])),
    }


def depth(obligation: dict[str, Any]) -> int:
    return int(obligation.get("floor") or obligation.get("level") or 1)


def contraction(previous: dict[str, Any], candidate: dict[str, Any]) -> list[str]:
    """Name every way a proposed obligation would ask for less than the stored one."""
    findings = []
    if previous["mandatory"] and not candidate.get("mandatory", True):
        findings.append("mandatory obligation would become optional")
    if CRITICALITY.index(previous["criticality"]) > CRITICALITY.index(
        candidate.get("criticality", "LOW")
    ):
        findings.append("criticality would be lowered")
    if previous["enforced"] and not candidate.get("enforced", True):
        findings.append("enforced obligation would stop being enforced")
    dropped = set(previous["acceptable_proof_capabilities"]) - set(
        candidate.get("acceptable_proof_capabilities", [])
    )
    if dropped:
        findings.append("proof capabilities would be dropped: " + ", ".join(sorted(dropped)))
    if depth(candidate) < depth(previous):
        findings.append("required proof depth would be lowered")
    if previous["required_verifiers"] and not candidate.get("required_verifiers"):
        findings.append("the claim would be left with no verifier at all")
    return findings


def plan_digest(obligations: list[dict[str, Any]]) -> str:
    return digest(
        sorted(
            (
                o["id"],
                o["claim"],
                o["criticality"],
                o["mandatory"],
                o["enforced"],
                sorted(o["acceptable_proof_capabilities"]),
            )
            for o in obligations
        )
    )
