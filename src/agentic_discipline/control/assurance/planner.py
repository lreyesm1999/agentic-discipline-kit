"""Choose the cheapest evidence route that is still sufficient for each obligation.

Cheapest sufficient, not least work: a route may not drop below the level the
obligation's criticality requires, and deterministic proof always wins over judgment.
"""

from __future__ import annotations

from typing import Any

from ..contracts import digest
from .model import HUMAN_ONLY
from .registry import COSTS, Registry

# `floor` is the escalation counter: the shallowest verifier class still allowed for this
# claim. It starts at the cheapest and rises only when a route fails to settle the claim,
# so a deeper strategy replaces the one that could not answer instead of joining it.
# Depth required by risk is expressed by the compiler, which adds a falsification
# obligation for HIGH and CRITICAL work rather than by forbidding cheap proof here.
SHALLOWEST = 1
DEEPEST = 4
# Falsification first: given equal cost, prefer a route that tries to break the claim.
FALSIFYING = {"falsification", "property", "invariant", "test_strength", "falsification_review"}


def pool(task: dict[str, Any], registry: Registry) -> list[dict[str, Any]]:
    """The concrete, already approved verifiers this task declared, with capabilities."""
    return [
        {
            "digest": digest(spec),
            "kind": spec["kind"],
            "command": spec["command"],
            "acceptance": spec["acceptance"],
            "descriptor": registry.get(spec["kind"]),
        }
        for spec in task["verification"]
    ]


def _rank(entry: dict[str, Any], capability: str) -> tuple[int, int, int, str]:
    descriptor = entry["descriptor"]
    return (
        0 if descriptor["deterministic"] else 1,
        COSTS.index(descriptor["cost"]),
        0 if capability in FALSIFYING else 1,
        entry["kind"],
    )


def _supplying(
    specs: list[dict[str, Any]], capability: str, level: int, floor: int
) -> list[dict[str, Any]]:
    return sorted(
        (
            e
            for e in specs
            if capability in e["descriptor"]["capabilities"]
            and floor <= e["descriptor"]["level"] <= level
        ),
        key=lambda e: _rank(e, capability),
    )


def plan_for(
    obligation: dict[str, Any],
    specs: list[dict[str, Any]],
    registry: Registry,
    *,
    floor: int | None = None,
) -> dict[str, Any]:
    """One sufficient capability discharges the claim; alternatives are not conjunctions."""
    acceptable = list(obligation["acceptable_proof_capabilities"])
    minimum = SHALLOWEST if floor is None else floor
    if acceptable and set(acceptable) <= HUMAN_ONLY:
        # A named human verifier, so a recorded human verdict resolves this claim the same
        # way a process does: bound to the obligation, and stale when its inputs move.
        return {
            "level": 4,
            "selected": [f"human:{obligation['id']}"],
            "covered": ["human_judgment"],
            "route": "human resolution; no automated verifier can settle this claim",
            "human_required": True,
            "unsatisfiable": [],
            "deterministic_available": [],
        }
    deterministic = sorted(set(acceptable) & registry.deterministic_capabilities())
    for level in range(minimum, DEEPEST + 1):
        candidates = [
            (capability, entry)
            for capability in sorted(acceptable)
            for entry in _supplying(specs, capability, level, minimum)[:1]
        ]
        # Deterministic dominance: while a declared deterministic verifier can reach one
        # of the acceptable capabilities, a judgment route is not a substitute for it.
        preferred = [item for item in candidates if item[1]["descriptor"]["deterministic"]]
        chosen = sorted(preferred or candidates, key=lambda item: _rank(item[1], item[0]))
        if not chosen:
            continue
        capability, entry = chosen[0]
        return {
            "level": max(level, entry["descriptor"]["level"]),
            "selected": [entry["digest"]],
            "covered": [capability],
            "route": f"{entry['kind']} supplies {capability} "
            f"({entry['descriptor']['evidence_class']}, {entry['descriptor']['cost']} cost)",
            "human_required": entry["descriptor"]["evidence_class"] == "HUMAN",
            "unsatisfiable": [],
            "deterministic_available": deterministic,
        }
    return {
        "level": minimum,
        "selected": [],
        "covered": [],
        "route": "no declared verifier supplies an acceptable capability at depth "
        f"{minimum} or deeper: {', '.join(sorted(acceptable)) or 'none declared'}",
        "human_required": False,
        "unsatisfiable": sorted(acceptable),
        "deterministic_available": deterministic,
    }


def contract_level(obligation: dict[str, Any], specs: list[dict[str, Any]]) -> int:
    selected = set(obligation["required_verifiers"])
    levels = [e["descriptor"]["level"] for e in specs if e["digest"] in selected]
    return max(levels) if levels else 1


def plan(
    task: dict[str, Any],
    obligations: list[dict[str, Any]],
    registry: Registry,
    *,
    floors: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Attach a route to every obligation; contract obligations keep their own verifiers."""
    specs = pool(task, registry)
    result = []
    for obligation in obligations:
        route: dict[str, Any]
        if obligation["derivation"] == "CONTRACT":
            route = {
                "level": contract_level(obligation, specs),
                "selected": sorted(obligation["required_verifiers"]),
                "covered": sorted(obligation["acceptable_proof_capabilities"]),
                "route": "verifiers the task contract bound to this acceptance criterion",
                "human_required": False,
                "unsatisfiable": [],
                "deterministic_available": sorted(
                    set(obligation["acceptable_proof_capabilities"])
                    & registry.deterministic_capabilities()
                ),
            }
        else:
            route = plan_for(
                obligation, specs, registry, floor=(floors or {}).get(obligation["id"])
            )
        result.append(
            {
                **obligation,
                "required_verifiers": sorted(route["selected"]),
                "plan": route,
                "level": route["level"],
            }
        )
    return result
