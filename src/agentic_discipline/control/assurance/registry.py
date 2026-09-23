"""What a verifier can prove, how strong that proof is, and what it costs to get it.

The engine reasons about capabilities. A project's task contract keeps supplying the
concrete argv, so nothing here is coupled to pytest, dotnet test, jest or any other tool.
"""

from __future__ import annotations

from typing import Any

from ..contracts import require
from .model import CAPABILITIES, COSTS, EVIDENCE_CLASSES, LEVELS

# `id` is the verifier kind a task contract declares. `level` is the progressive
# assurance level at which this class of proof becomes eligible.
#
# Capabilities are deliberately narrow. A unit suite proves unit behaviour; it does not
# also get to stand for regression, because then any project with unit tests would already
# satisfy a claim about historical data it never examined.
DEFAULTS: tuple[dict[str, Any], ...] = (
    {
        "id": "unit",
        "capabilities": ["unit"],
        "evidence_class": "DETERMINISTIC",
        "cost": "low",
        "level": 1,
        "supports_incremental": True,
    },
    {
        "id": "integration",
        "capabilities": ["integration", "behavioral"],
        "evidence_class": "DETERMINISTIC",
        "cost": "medium",
        "level": 2,
        "supports_incremental": False,
    },
    {
        "id": "acceptance",
        "capabilities": ["acceptance", "behavioral"],
        "evidence_class": "DETERMINISTIC",
        "cost": "medium",
        "level": 1,
        "supports_incremental": True,
    },
    {
        "id": "regression",
        # Not `data_preservation`: a regression suite compares behaviour, and a claim about
        # data that survived a migration needs a verifier that says it examines that data.
        "capabilities": ["regression", "historical_stability"],
        "evidence_class": "DETERMINISTIC",
        "cost": "medium",
        "level": 2,
        "supports_incremental": True,
    },
    {
        "id": "property",
        "capabilities": ["property", "invariant", "falsification"],
        "evidence_class": "DETERMINISTIC",
        "cost": "medium",
        "level": 2,
        "supports_incremental": False,
    },
    {
        "id": "contract",
        "capabilities": ["contract_compatibility", "schema_compatibility"],
        "evidence_class": "DETERMINISTIC",
        "cost": "low",
        "level": 1,
        "supports_incremental": True,
    },
    {
        "id": "schema",
        "capabilities": ["schema_compatibility", "migration_safety"],
        "evidence_class": "DETERMINISTIC",
        "cost": "low",
        "level": 1,
        "supports_incremental": True,
    },
    {
        "id": "migration",
        "capabilities": ["migration_safety", "data_preservation"],
        "evidence_class": "DETERMINISTIC",
        "cost": "high",
        "level": 2,
        "supports_incremental": False,
    },
    {
        "id": "security",
        "capabilities": ["security", "authorization_boundary"],
        "evidence_class": "DETERMINISTIC",
        "cost": "medium",
        "level": 2,
        "supports_incremental": False,
    },
    {
        "id": "architecture",
        "capabilities": ["architecture"],
        "evidence_class": "DETERMINISTIC",
        "cost": "low",
        "level": 1,
        "supports_incremental": True,
    },
    {
        "id": "static",
        "capabilities": ["static_analysis"],
        "evidence_class": "DETERMINISTIC",
        "cost": "low",
        "level": 1,
        "supports_incremental": True,
    },
    {
        "id": "coverage",
        "capabilities": ["coverage"],
        "evidence_class": "MEASURED",
        "cost": "medium",
        "level": 2,
        "supports_incremental": False,
    },
    {
        "id": "reference",
        "capabilities": ["reference_comparison"],
        "evidence_class": "DETERMINISTIC",
        "cost": "low",
        "level": 1,
        "supports_incremental": True,
    },
    {
        "id": "mutation",
        "capabilities": ["falsification", "test_strength"],
        "evidence_class": "DETERMINISTIC",
        "cost": "high",
        "level": 3,
        "supports_incremental": True,
    },
    {
        "id": "adversarial",
        "capabilities": ["falsification_review"],
        "evidence_class": "AGENT_JUDGMENT",
        "cost": "high",
        "level": 3,
        "supports_incremental": False,
    },
    {
        "id": "reference-review",
        "capabilities": ["qualitative_reference_comparison"],
        "evidence_class": "AGENT_JUDGMENT",
        "cost": "medium",
        "level": 3,
        "supports_incremental": False,
    },
    {
        "id": "human",
        "capabilities": ["human_judgment"],
        "evidence_class": "HUMAN",
        "cost": "manual",
        "level": 4,
        "supports_incremental": False,
    },
)
UNDECLARED: dict[str, Any] = {
    "capabilities": [],
    "evidence_class": "MEASURED",
    "cost": "medium",
    "level": 1,
    "supports_incremental": False,
    "deterministic": False,
    "declared": False,
    "ecosystems": ["*"],
    "required_inputs": [],
    "produced_artifacts": [],
    "note": "kind is not in the capability registry; register it to let the planner use it",
}


def descriptor_contract(data: dict[str, Any]) -> None:
    required = {"id", "capabilities", "evidence_class", "cost", "level"}
    require(
        required <= data.keys(),
        "INVALID_CAPABILITY",
        f"Missing verifier capability fields: {sorted(required - data.keys())}",
    )
    require(
        isinstance(data["id"], str) and bool(data["id"].strip()),
        "INVALID_CAPABILITY",
        "Verifier kind must be nonempty text",
    )
    require(
        isinstance(data["capabilities"], list)
        and bool(data["capabilities"])
        and set(data["capabilities"]) <= CAPABILITIES,
        "INVALID_CAPABILITY",
        "Declare at least one known capability",
    )
    require(
        data["evidence_class"] in EVIDENCE_CLASSES,
        "INVALID_CAPABILITY",
        "Unknown evidence class",
    )
    require(data["cost"] in COSTS, "INVALID_CAPABILITY", "Unknown cost class")
    require(data["level"] in LEVELS, "INVALID_CAPABILITY", "Unknown assurance level")
    require(
        data["evidence_class"] != "DETERMINISTIC" or data["cost"] != "manual",
        "INVALID_CAPABILITY",
        "A manual verifier cannot declare deterministic evidence",
    )
    for key in ("ecosystems", "required_inputs", "produced_artifacts"):
        require(
            isinstance(data.get(key, []), list)
            and all(isinstance(x, str) and x for x in data.get(key, [])),
            "INVALID_CAPABILITY",
            f"Invalid list: {key}",
        )


def normalized(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": data["id"],
        "capabilities": sorted(set(data["capabilities"])),
        "evidence_class": data["evidence_class"],
        "cost": data["cost"],
        "level": data["level"],
        "supports_incremental": bool(data.get("supports_incremental", False)),
        "ecosystems": list(data.get("ecosystems", ["*"])),
        "required_inputs": list(data.get("required_inputs", [])),
        "produced_artifacts": list(data.get("produced_artifacts", [])),
        "deterministic": data["evidence_class"] == "DETERMINISTIC",
        "declared": True,
    }


class Registry:
    """Built-in descriptors, overridden only by an owner-registered project descriptor."""

    def __init__(self, records: list[dict[str, Any]] | None = None) -> None:
        self.entries = {d["id"]: normalized(d) for d in DEFAULTS}
        for record in records or []:
            descriptor_contract(record)
            self.entries[record["id"]] = normalized(record)

    def describe(self) -> list[dict[str, Any]]:
        return [self.entries[k] for k in sorted(self.entries)]

    def get(self, kind: str) -> dict[str, Any]:
        return self.entries.get(kind, {**UNDECLARED, "id": kind})

    def capabilities(self, kind: str) -> set[str]:
        return set(self.get(kind)["capabilities"])

    def supplying(self, capability: str) -> list[dict[str, Any]]:
        """Cheapest first, then the earliest level, then a stable name."""
        return sorted(
            (e for e in self.entries.values() if capability in e["capabilities"]),
            key=lambda e: (COSTS.index(e["cost"]), e["level"], e["id"]),
        )

    def deterministic_capabilities(self) -> set[str]:
        return {c for e in self.entries.values() if e["deterministic"] for c in e["capabilities"]}
