"""Explicit 2.0 to 2.1 upgrade: idempotent, backed up first, and reversible.

What can be reconstructed is reconstructed. What cannot keeps legacy provenance rather
than a plausible relationship nobody measured.
"""

from __future__ import annotations

import time
from typing import Any

from ..contracts import require
from . import service
from .registry import Registry

SCHEMA_VERSION = "2"


def _set_version(plane: Any, value: str) -> None:
    plane.store.db.execute("UPDATE meta SET value=? WHERE key='schema_version'", (value,))
    plane.store.schema_version = int(value)


def plan(plane: Any) -> dict[str, Any]:
    """What the upgrade would do, without touching anything."""
    tasks = plane.store.list("task")
    evidence = plane.store.list("evidence")
    return {
        "dry_run": True,
        "from_schema": str(plane.store.schema_version),
        "to_schema": SCHEMA_VERSION,
        "tasks": [t["id"] for t in tasks],
        "acceptance_criteria": sum(len(t["acceptance"]) for t in tasks),
        "evidence_records": len(evidence),
        "already_migrated": plane.store.schema_version >= 2,
        "becomes": [
            "each acceptance criterion becomes a mandatory proof obligation",
            "policy obligations from the declared scope are recorded but not enforced until"
            " the actual change confirms them",
            "existing evidence keeps its artefacts and gains legacy assurance provenance",
            "completion starts refusing a task that holds mandatory proof debt",
        ],
        "unreconstructible": [
            "which obligation a legacy evidence record was produced for, beyond its"
            " acceptance criterion index"
        ],
        "writes": ["knowledge database", "backup file when --backup is given"],
    }


def migrate(plane: Any, *, dry_run: bool = False) -> dict[str, Any]:
    if dry_run:
        return plan(plane)
    registry = Registry(plane.store.list("verifier_capability"))
    previous = str(plane.store.schema_version)
    reactivated: list[str] = []
    with plane.store.transaction():
        for obligation in plane.store.list("obligation"):
            if obligation.get("reverted"):
                plane.store.put(
                    "obligation",
                    {**obligation, "reverted": False, "updated_at": time.time()},
                    expected=obligation["version"],
                    actor="local-owner",
                )
                reactivated.append(obligation["id"])
        classified = []
        for evidence in plane.store.list("evidence"):
            if evidence.get("assurance_provenance"):
                continue
            descriptor = registry.get(evidence["kind"])
            plane.store.put(
                "evidence",
                {
                    **evidence,
                    "assurance_provenance": "LEGACY",
                    "evidence_class": evidence.get("evidence_class")
                    or (descriptor["evidence_class"] if descriptor.get("declared") else "MEASURED"),
                },
                expected=evidence["version"],
                actor="local-owner",
            )
            classified.append(evidence["id"])
        _set_version(plane, SCHEMA_VERSION)
        plane.store.event(
            "local-owner",
            "assurance.migrate",
            {"from": previous, "to": SCHEMA_VERSION, "evidence": len(classified)},
        )
    compiled = {}
    for task in plane.store.list("task"):
        compiled[task["id"]] = service.compile_plan(plane, task["id"], phase="INITIAL")
    with plane.store.transaction():
        record = plane.store.put(
            "assurance_migration",
            {
                "from_schema": previous,
                "to_schema": SCHEMA_VERSION,
                "status": "APPLIED",
                "tasks": sorted(compiled),
                "obligations": sorted(o["id"] for o in plane.store.list("obligation")),
                "reclassified_evidence": classified,
                "reactivated": reactivated,
                "created_at": time.time(),
            },
            actor="local-owner",
        )
    return {
        "migrated": True,
        "from_schema": previous,
        "to_schema": SCHEMA_VERSION,
        "migration_id": record["id"],
        "obligations": len(record["obligations"]),
        "tasks": sorted(compiled),
        "reclassified_evidence": len(classified),
        "legacy_provenance": "evidence keeps its artefacts; its obligation link is the"
        " acceptance criterion it was recorded against, and nothing more",
    }


def rollback(plane: Any, identifier: str, reason: str) -> dict[str, Any]:
    """Return to 2.0 behaviour, keeping every record and artefact for audit."""
    require(bool(reason.strip()), "REASON_REQUIRED", "Rollback requires a reason")
    record = plane.store.get(identifier, "assurance_migration")
    require(record["status"] == "APPLIED", "INVALID_MIGRATION", "Migration is not applied")
    reverted = []
    with plane.store.transaction():
        for obligation in plane.store.list("obligation"):
            if obligation["id"] not in set(record["obligations"]):
                continue
            plane.store.put(
                "obligation",
                {**obligation, "reverted": True, "updated_at": time.time()},
                expected=obligation["version"],
                actor="local-owner",
            )
            reverted.append(obligation["id"])
        _set_version(plane, record["from_schema"])
        updated = plane.store.put(
            "assurance_migration",
            {**record, "status": "ROLLED_BACK", "rollback_reason": reason},
            expected=record["version"],
            actor="local-owner",
        )
        plane.store.event(
            "local-owner",
            "assurance.rollback",
            {"migration": identifier, "reason": reason, "obligations": reverted},
        )
    return {
        "rolled_back": True,
        "migration": updated,
        "schema_version": record["from_schema"],
        "obligations_retired": len(reverted),
        "preserved": "obligations, plans, waivers and evidence remain readable for audit",
    }
