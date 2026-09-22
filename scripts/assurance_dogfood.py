#!/usr/bin/env python3
"""Run the Adaptive Assurance Engine on this repository's own 2.1 work.

Every verdict below comes from a real pytest process executed in this checkout, and every
state change is read back from the persisted records. The run demonstrates, in order:
obligation compilation, plan creation, verifier execution, evidence resolution, staleness,
assurance expansion, refused contraction, conflicting evidence, blocked completion, and
the audited waiver that is the only way to close a claim without proof.

    python scripts/assurance_dogfood.py --reset --output docs/v2.1/evidence/dogfood.json

`--reset` removes `.agentic/control/`, which is this script's own gitignored state.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentic_discipline.control.assurance import service
from agentic_discipline.control.assurance.resolver import obligations_for
from agentic_discipline.control.contracts import ControlError
from agentic_discipline.control.plane import Plane, adopt, state_dir
from agentic_discipline.control.verification import complete

ROOT = Path(__file__).resolve().parents[1]
ASSURANCE = "src/agentic_discipline/control/assurance"
SCRATCH = "docs/v2.1/evidence/dogfood"
BUDGET = {
    "max_runtime": 1800,
    "max_retries": 12,
    "max_files": 40,
    "max_lines": 40000,
    "max_external_calls": 0,
    "max_cost": 0,
}


def suite(*paths: str) -> list[str]:
    return [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *paths]


SCENARIOS = suite("tests/control/test_assurance_scenarios.py")
GUARDS = suite("tests/control/test_assurance_failures.py", "tests/control/test_assurance_edges.py")
PROPERTIES = suite("tests/control/test_assurance_properties.py")
FAILING = [sys.executable, "-c", "raise SystemExit(1)"]


def contract(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "objective": "Prove the Adaptive Assurance Engine on its own repository",
        "scope": [ASSURANCE, "tests/control", SCRATCH],
        "out_of_scope": ["release packaging"],
        "requirements": [],
        "acceptance": [
            "The twelve assurance scenarios hold end to end",
            "The engine refuses the tampering and failure cases",
        ],
        "dependencies": [],
        "boundaries": ["assurance engine"],
        "context": [],
        "verification": [
            {"kind": "acceptance", "command": SCENARIOS, "acceptance": [0]},
            {"kind": "unit", "command": GUARDS, "acceptance": [1]},
            {"kind": "property", "command": PROPERTIES, "acceptance": []},
        ],
        "required_evidence": ["acceptance", "unit", "property"],
        "rollback": "Revert the assurance package and its tests",
        "definition_of_done": "Every mandatory obligation resolved by current evidence",
        "risk": "HIGH",
        "budget": dict(BUDGET),
    }
    base.update(overrides)
    return base


def checkpoint(action: str) -> dict[str, Any]:
    return {
        "completed_work": ["implemented the assurance engine and its tests"],
        "modified_files": [ASSURANCE],
        "commands_run": [" ".join(SCENARIOS)],
        "tests_run": ["assurance scenarios", "assurance guards", "assurance properties"],
        "test_results": ["recorded as evidence, not narrated"],
        "failures": [],
        "discoveries": ["the protected-path obligation was unreachable and was replaced"],
        "assumptions": [],
        "pending_issues": [],
        "current_hypothesis": "Obligation state, not agent confidence, governs completion",
        "next_action": action,
    }


def prepare(plane: Plane, data: dict[str, Any], name: str) -> tuple[str, str]:
    for verifier in data["verification"]:
        plane.approve_command(verifier["command"])
    task = plane.create_task(data)
    plane.ready(task["id"])
    session = plane.join(name, ["code", "testing"])["session"]
    plane.claim(task["id"], session, seconds=3600)
    return str(task["id"]), str(session)


def obligation_view(plane: Plane, task_id: str) -> list[dict[str, Any]]:
    report = service.status(plane, task_id)["tasks"][0]
    return [
        {
            "id": o["id"],
            "claim": o["claim"],
            "derivation": o["derivation"],
            "criticality": o["criticality"],
            "enforced": o["enforced"],
            "status": o["status"],
        }
        for o in report["obligations"]
    ]


def snapshot(plane: Plane, task_id: str, label: str) -> dict[str, Any]:
    report = service.status(plane, task_id)["tasks"][0]
    return {
        "step": label,
        "required": report["required"],
        "counts": report["counts"],
        "proof_debt": report["proof_debt"],
        "decision": report["decision"]["decision"],
        "obligations": obligation_view(plane, task_id),
    }


def run() -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    started = time.time()
    adoption = adopt(ROOT)
    scratch = ROOT / SCRATCH
    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / "README.md").write_text(
        "Scratch area the dogfood run uses as the change it reasons about.\n", encoding="utf-8"
    )
    with Plane(ROOT) as plane:
        if plane.store.schema_version < 2:
            from agentic_discipline.control.assurance import migration

            migration.migrate(plane)
        task, session = prepare(plane, contract(), "dogfood-assurance")

        # 1 obligation compilation and plan creation, before anything is verified.
        initial = service.compile_plan(plane, task, phase="INITIAL")
        steps.append({**snapshot(plane, task, "compiled from the declared contract")})
        plan_created = {
            "phase": initial["phase"],
            "obligations": len(initial["obligations"]),
            "plan_digest": initial["plan_digest"],
            "signals": initial["signals"],
        }

        # 2 verifier execution and evidence resolution, from real processes.
        outcome = service.verify(plane, task, session)
        steps.append({**snapshot(plane, task, "after running the declared verifiers")})
        executions = [
            {
                "kind": record["kind"],
                "command": record["command"][-1],
                "result": record["result"],
                "exit_code": record["exit_code"],
                "evidence_class": record["evidence_class"],
                "artifact": record["artifact_ref"],
            }
            for execution in outcome["executions"]
            for record in execution["evidence"]
        ]

        # 3 staleness: a proven file moves, and the claim stops being supported.
        target = ROOT / ASSURANCE / "model.py"
        original = target.read_bytes()
        target.write_bytes(original + b"\n# dogfood: this comment invalidates the proof above\n")
        steps.append({**snapshot(plane, task, "after editing a file the proof rested on")})
        target.write_bytes(original)
        steps.append({**snapshot(plane, task, "after restoring that file byte for byte")})

        # 4 assurance expansion: the change grows a surface the contract never declared.
        (scratch / "migration-notes.md").write_text(
            "The dogfood change now touches a migration surface.\n", encoding="utf-8"
        )
        expanded = service.reconcile(plane, task)
        steps.append({**snapshot(plane, task, "after the diff reached a migration surface")})

        # 5 refused contraction: removing that surface does not remove its obligation.
        (scratch / "migration-notes.md").unlink()
        retained = service.reconcile(plane, task)
        steps.append({**snapshot(plane, task, "after removing the surface again")})

        # 6 blocked completion while a mandatory claim is open.
        plane.checkpoint(task, session, checkpoint("Resolve or waive the migration claim"))
        service.verify(plane, task, session)
        blocked: dict[str, Any] = {"completed": True}
        try:
            complete(plane, task, session)
        except ControlError as refusal:
            blocked = {"completed": False, "code": refusal.code, "message": str(refusal)}
        steps.append({**snapshot(plane, task, "when completion was attempted")})

        # 7 conflicting evidence, on a second real task in the same repository.
        plane.release(task, session)
        conflict_task, conflict_session = prepare(
            plane,
            contract(
                objective="Show what the engine does with contradictory evidence",
                acceptance=["The assurance properties hold"],
                verification=[
                    {"kind": "property", "command": PROPERTIES, "acceptance": [0]},
                    {"kind": "unit", "command": FAILING, "acceptance": [0]},
                ],
                required_evidence=["property", "unit"],
                risk="STANDARD",
            ),
            "dogfood-conflict",
        )
        service.compile_plan(plane, conflict_task, phase="INITIAL")
        conflict_outcome = service.verify(plane, conflict_task, conflict_session)
        conflict = {
            **snapshot(plane, conflict_task, "with one passing and one failing verifier"),
            "decision_reasons": conflict_outcome["decision"]["reasons"],
        }
        plane.release(conflict_task, conflict_session)

        # 8 the audited waiver, and only then completion.
        plane.claim(task, session, seconds=3600)
        migration_claim = next(
            o for o in obligations_for(plane, task) if "MIG-SAFE" in o["origin"]["policy_ids"]
        )
        waiver = service.waive(
            plane,
            migration_claim["id"],
            "the migration surface was removed from the change, so the claim has no subject",
            "code owner (@lreyesm1999)",
        )
        plane.checkpoint(task, session, checkpoint("Complete the task"))
        service.verify(plane, task, session)
        completion = complete(plane, task, session)
        steps.append({**snapshot(plane, task, "after the recorded waiver")})
        integrity = service.integrity(plane)
        explained = service.explain(plane, migration_claim["id"])
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "repository": str(ROOT),
            "commit": adoption.get("project", {}).get("baseline_commit")
            or adoption.get("commit", ""),
            "runtime_seconds": round(time.time() - started, 3),
            "fixture": "this repository; every verdict comes from a real pytest process",
            "task": task,
            "plan_created": plan_created,
            "verifier_executions": executions,
            "expansion": {
                "added": expanded["expansion"]["added"],
                "signals": expanded["signals"],
                "retained_after_removal": retained["expansion"]["retained"],
                "refused_contractions": retained["refused_contractions"],
            },
            "blocked_completion": blocked,
            "conflicting_evidence": conflict,
            "waiver": {
                "obligation_id": waiver["waiver"]["obligation_id"],
                "criticality": waiver["waiver"]["criticality"],
                "reason": waiver["waiver"]["reason"],
                "authorization": waiver["waiver"]["authorization"],
                "status_when_waived": waiver["waiver"]["status_when_waived"],
            },
            "explained_waived_claim": {
                "claim": explained["claim"],
                "status": explained["status"],
                "required_because": explained["required_because"],
            },
            "steps": steps,
            "final_task_state": completion["state"],
            "integrity": {"status": integrity["status"], "checked": integrity["checked"]},
            "audit": plane.store.audit(),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--reset", action="store_true", help="remove this script's own gitignored control state"
    )
    arguments = parser.parse_args()
    directory = state_dir(ROOT)
    if arguments.reset:
        shutil.rmtree(directory, ignore_errors=True)
    elif directory.exists():
        parser.error(f"{directory} already exists; pass --reset to start from a clean run")
    report = run()
    shutil.rmtree(ROOT / SCRATCH, ignore_errors=True)
    output = json.dumps(report, indent=2) + "\n"
    if arguments.output:
        arguments.output.write_text(output, encoding="utf-8")
    print(output, end="")
    expected = (
        report["final_task_state"] == "COMPLETED"
        and report["blocked_completion"]["completed"] is False
        and report["conflicting_evidence"]["counts"].get("CONFLICTED") == 1
        and report["integrity"]["status"] == "PASS"
        and report["audit"]["status"] == "PASS"
    )
    return 0 if expected else 1


if __name__ == "__main__":
    raise SystemExit(main())
