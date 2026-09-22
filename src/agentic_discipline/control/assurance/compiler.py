"""Derive the obligations a change must discharge, deterministically and with provenance.

The compiler never invents product requirements. Every obligation is traceable either to
an executable contract the project already wrote, or to a repository policy applied to
observed paths.
"""

from __future__ import annotations

import re
from typing import Any

from ...risk import PATTERNS
from ..contracts import digest
from . import impact
from .model import obligation_id, stronger
from .registry import Registry

# (policy id, risk signal, claim, acceptable capabilities, minimum criticality)
POLICY_RULES: tuple[tuple[str, str, str, tuple[str, ...], str], ...] = (
    (
        "SEC-AUTHZ",
        "auth",
        "Unauthorized callers cannot reach the operations this change touches.",
        # Not `acceptance`: any acceptance suite would then close an authorization claim it
        # never examined. The capability has to be one a verifier says it provides.
        ("authorization_boundary", "security"),
        "HIGH",
    ),
    (
        "FIN-STABLE",
        "money",
        "Financial results for existing data are unchanged by this change.",
        # Not `property`: a property test proves an invariant, which is a different claim
        # from "the numbers this already produced have not moved".
        ("historical_stability", "regression"),
        "CRITICAL",
    ),
    (
        "MIG-SAFE",
        "migration",
        "The migration preserves the data that already exists.",
        # Not `regression`: this claim is about persisted data, so it takes a verifier that
        # says it examines persisted data. Register one if your regression suite does.
        ("migration_safety", "data_preservation"),
        "CRITICAL",
    ),
    (
        "API-COMPAT",
        "public_api",
        "The published interface stays compatible for existing callers.",
        ("contract_compatibility", "schema_compatibility"),
        "HIGH",
    ),
    (
        "CONC-SAFE",
        "concurrency",
        "Concurrent execution cannot observe or produce an inconsistent state.",
        ("property", "invariant", "integration"),
        "HIGH",
    ),
    (
        "SEC-GENERAL",
        "security",
        "The change introduces no new way to read or forge protected data.",
        ("security", "static_analysis"),
        "HIGH",
    ),
    (
        "CRYPTO-SAFE",
        "crypto",
        "Cryptographic behaviour matches its specified algorithm and parameters.",
        ("property", "security", "regression"),
        "CRITICAL",
    ),
    (
        "DEL-SAFE",
        "destructive",
        "Destructive operations remove only what their contract allows.",
        ("regression", "acceptance", "property"),
        "HIGH",
    ),
    (
        "ARCH-BOUND",
        "architecture",
        "Declared architecture boundaries are not crossed by this change.",
        ("architecture", "static_analysis"),
        "HIGH",
    ),
    (
        "INFRA-SAFE",
        "infra",
        "Deployment and pipeline configuration remains executable as declared.",
        ("static_analysis", "integration"),
        "STANDARD",
    ),
)
FALSIFICATION_RULE = (
    "TEST-STRENGTH",
    "The tests covering this change detect meaningful implementation errors.",
    ("falsification", "test_strength", "falsification_review"),
)
# Protected contracts are not covered by an obligation here. The existing change check
# refuses a protected edit inside a task outright, which is a stronger control than a
# claim to be discharged, and an obligation nothing can ever reach would only mislead.
HUMAN_RULE = (
    "HUMAN-ACCEPTANCE",
    "A human explicitly accepted this critical change.",
    ("human_judgment",),
)


def signals(paths: list[str]) -> list[str]:
    """Risk signals the observed paths raise, using the existing deterministic patterns."""
    text = "\n".join(sorted(paths)).lower()
    return sorted(name for name, pattern in PATTERNS.items() if re.search(pattern, text))


def _obligation(
    task: dict[str, Any],
    *,
    origin_key: str,
    claim: str,
    capabilities: tuple[str, ...] | list[str],
    criticality: str,
    derivation: str,
    reason: str,
    paths: list[str],
    phase: str,
    enforced: bool,
    acceptance_ids: list[int] | None = None,
    policy_ids: list[str] | None = None,
    requirement_ids: list[str] | None = None,
    architecture_ids: list[str] | None = None,
    verifiers: list[str] | None = None,
    mandatory: bool = True,
) -> dict[str, Any]:
    return {
        "id": obligation_id(task["id"], origin_key),
        "task_id": task["id"],
        "claim": claim,
        "origin": {
            "requirement_ids": sorted(requirement_ids if requirement_ids is not None else []),
            "acceptance_ids": sorted(acceptance_ids or []),
            "policy_ids": sorted(policy_ids or []),
            "architecture_ids": sorted(architecture_ids or []),
            "generated_reason": reason,
        },
        "derivation": derivation,
        "criticality": criticality,
        "mandatory": mandatory,
        "status": "UNRESOLVED",
        "phase": phase,
        "enforced": enforced,
        "acceptable_proof_capabilities": sorted(set(capabilities)),
        "required_verifiers": sorted(set(verifiers or [])),
        "affected_paths": sorted(set(paths)),
        "affected_symbols": [],
        "dependencies": [],
    }


def contract_obligations(
    task: dict[str, Any], registry: Registry, phase: str
) -> list[dict[str, Any]]:
    """One obligation per acceptance criterion, bound to the verifiers that cover it."""
    result = []
    for index, criterion in enumerate(task["acceptance"]):
        specs = [v for v in task["verification"] if index in v["acceptance"]]
        capabilities: set[str] = set()
        for spec in specs:
            capabilities |= registry.capabilities(spec["kind"])
        result.append(
            _obligation(
                task,
                origin_key=f"acceptance:{index}",
                claim=criterion,
                capabilities=sorted(capabilities),
                criticality=task["risk"],
                derivation="CONTRACT",
                reason="acceptance criterion declared in the task contract",
                paths=task["scope"],
                phase=phase,
                enforced=True,
                acceptance_ids=[index],
                requirement_ids=task["requirements"],
                architecture_ids=task["boundaries"],
                verifiers=[digest(spec) for spec in specs],
            )
        )
    return result


def policy_obligations(
    task: dict[str, Any],
    paths: list[str],
    *,
    phase: str,
    enforced: bool,
    derivation: str = "POLICY",
    because: str = "",
) -> list[dict[str, Any]]:
    result = []
    for policy_id, signal, claim, capabilities, minimum in POLICY_RULES:
        matched = [p for p in paths if re.search(PATTERNS[signal], p.lower())]
        if not matched:
            continue
        reason = f"observed {signal} surface in {', '.join(sorted(matched)[:5])}"
        result.append(
            _obligation(
                task,
                origin_key=f"policy:{policy_id}",
                claim=claim,
                capabilities=capabilities,
                criticality=stronger(task["risk"], minimum),
                derivation=derivation,
                reason=reason + (f"; reached through {because}" if because else ""),
                paths=matched,
                phase=phase,
                enforced=enforced,
                policy_ids=[policy_id],
                requirement_ids=task["requirements"],
            )
        )
    return result


def human_obligation(
    task: dict[str, Any], paths: list[str], *, phase: str, enforced: bool
) -> list[dict[str, Any]]:
    """The explicit human acceptance the risk policy already requires of CRITICAL work."""
    if task["risk"] != "CRITICAL":
        return []
    policy_id, claim, capabilities = HUMAN_RULE
    observed = sorted(paths) or list(task["scope"])
    return [
        _obligation(
            task,
            origin_key=f"policy:{policy_id}",
            claim=claim,
            capabilities=capabilities,
            criticality="CRITICAL",
            derivation="POLICY",
            reason="CRITICAL risk requires a recorded human acceptance of "
            + ", ".join(observed[:5]),
            paths=observed,
            phase=phase,
            enforced=enforced,
            policy_ids=[policy_id],
            requirement_ids=task["requirements"],
            architecture_ids=task["boundaries"],
        )
    ]


def falsification_obligation(
    task: dict[str, Any], paths: list[str], *, phase: str, enforced: bool
) -> list[dict[str, Any]]:
    if task["risk"] not in {"HIGH", "CRITICAL"}:
        return []
    policy_id, claim, capabilities = FALSIFICATION_RULE
    return [
        _obligation(
            task,
            origin_key=f"policy:{policy_id}",
            claim=claim,
            capabilities=capabilities,
            criticality=task["risk"],
            derivation="POLICY",
            reason=f"{task['risk']} risk requires falsifying the strength of its tests",
            paths=paths or task["scope"],
            phase=phase,
            enforced=enforced,
            policy_ids=[policy_id],
            requirement_ids=task["requirements"],
        )
    ]


def impact_obligations(
    plane: Any, task: dict[str, Any], reach: dict[str, Any]
) -> list[dict[str, Any]]:
    """Expansion: what the change reaches beyond the paths it edited."""
    result = policy_obligations(
        task,
        reach["dependent_paths"],
        phase="RECONCILED",
        enforced=True,
        derivation="IMPACT",
        because="recorded dependencies of the changed files",
    )
    for identifier in reach["dependent_requirements"]:
        entity = plane.store.get(identifier, "entity")
        result.append(
            _obligation(
                task,
                origin_key=f"impact:requirement:{identifier}",
                claim=f"Requirement {entity['name']} still holds after this change.",
                capabilities=("regression", "acceptance", "integration"),
                criticality=stronger(task["risk"], "STANDARD"),
                derivation="IMPACT",
                reason=f"{entity['name']} depends on a file this change modified",
                paths=reach["changed_paths"],
                phase="RECONCILED",
                enforced=True,
                requirement_ids=[identifier],
                mandatory=entity["authority"] in {"human", "contract"},
            )
        )
    return result


def compile_obligations(
    plane: Any,
    task: dict[str, Any],
    registry: Registry,
    *,
    phase: str,
) -> dict[str, Any]:
    """Phase A reads the declared scope; phase B reads the diff the task actually made."""
    if phase == "INITIAL":
        paths, reach = list(task["scope"]), None
    else:
        paths = impact.changed_paths(plane, task)
        reach = impact.reached(plane, paths)
    enforced = phase == "RECONCILED"
    obligations = contract_obligations(task, registry, phase)
    obligations += policy_obligations(task, paths, phase=phase, enforced=enforced)
    obligations += human_obligation(task, paths, phase=phase, enforced=enforced)
    obligations += falsification_obligation(task, paths, phase=phase, enforced=enforced)
    if reach is not None:
        obligations += impact_obligations(plane, task, reach)
        symbols = reach["observed_symbols"]
        for obligation in obligations:
            obligation["affected_symbols"] = sorted(
                s
                for s in symbols
                if impact.in_scope(s.split("::")[0], obligation["affected_paths"])
            )
    # One policy rule can be raised twice in a compilation: by a changed path and by a path
    # the change reaches. Both copies come from the same rule for the same task, so they
    # agree on everything except where they were seen; the paths are combined.
    merged: dict[str, dict[str, Any]] = {}
    for obligation in obligations:
        previous = merged.get(obligation["id"])
        merged[obligation["id"]] = (
            obligation
            if previous is None
            else {
                **previous,
                "affected_paths": sorted(
                    set(previous["affected_paths"]) | set(obligation["affected_paths"])
                ),
            }
        )
    return {
        "phase": phase,
        "observed_paths": paths,
        "signals": signals(paths),
        "impact": reach,
        "obligations": [merged[k] for k in sorted(merged)],
    }
