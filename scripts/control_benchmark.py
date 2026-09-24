#!/usr/bin/env python3
"""Reproducible local control-plane benchmark with real verifier execution."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agentic_discipline.control.api import call
from agentic_discipline.control.assurance import service as assurance
from agentic_discipline.control.plane import Plane, adopt
from agentic_discipline.control.verification import complete, verify


def measure(operation: Callable[[], Any], repeats: int = 5) -> dict[str, float]:
    values = []
    for _ in range(repeats):
        start = time.perf_counter()
        operation()
        values.append((time.perf_counter() - start) * 1000)
    return {"median_ms": round(statistics.median(values), 3), "max_ms": round(max(values), 3)}


def run(count: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="agentic-benchmark-") as temporary:
        root = Path(temporary)
        for index in range(count):
            (root / f"module_{index}.py").write_text(
                f"def item_{index}():\n    return {index}\n", encoding="utf-8"
            )
        adoption = measure(lambda: adopt(root), 1)
        with Plane(root) as plane:
            data = json.loads(
                (Path(__file__).resolve().parents[1] / "examples/control/task.json").read_text()
            )
            data["scope"] = ["module_0.py"]
            data["acceptance"] = ["The observed module returns zero"]
            command = [
                sys.executable,
                "-B",
                "-c",
                "from module_0 import item_0; assert item_0() == 0",
            ]
            data["verification"][0].update(command=command, inputs=["module_0.py"])
            plane.approve_command(command)
            task = plane.create_task(data)["id"]
            plane.ready(task)
            session = plane.join("benchmark-worker", ["code", "terminal"])["session"]
            claim = measure(lambda: plane.claim(task, session), 1)
            cp = {
                k: []
                for k in (
                    "completed_work",
                    "modified_files",
                    "commands_run",
                    "tests_run",
                    "test_results",
                    "failures",
                    "discoveries",
                    "assumptions",
                    "pending_issues",
                )
            }
            cp.update(
                current_hypothesis="Execute assertion against the real fixture module",
                next_action="Run verifier",
            )
            checkpoint = measure(lambda: plane.checkpoint(task, session, cp))
            compile_plan = measure(lambda: assurance.compile_plan(plane, task, phase="INITIAL"), 3)
            proof = verify(plane, task, session)
            resolve = measure(lambda: assurance.status(plane, task), 3)
            reconcile = measure(lambda: assurance.reconcile(plane, task), 3)
            completed = complete(plane, task, session)
            # Staleness recalculation is measured after the claim it invalidates is proven,
            # which is the only moment the cost is the real one.
            (root / "module_0.py").write_text(
                "def item_0():\n    return 0  # revised\n", encoding="utf-8"
            )
            stale = measure(lambda: assurance.debt_report(plane, task), 3)
            assurance_state = assurance.status(plane, task)["tasks"][0]
            status = measure(lambda: call(plane, "status", {}))
            query = measure(lambda: plane.knowledge.query("item_500" if count > 500 else "item_0"))
            context = plane.context(task)
            results = {
                "adoption": adoption,
                "status": status,
                "claim": claim,
                "checkpoint": checkpoint,
                "knowledge_query": query,
                "assurance_compile": compile_plan,
                "assurance_reconcile": reconcile,
                "assurance_resolve": resolve,
                "assurance_stale_recalculation": stale,
            }
            limits = {
                "status": 300,
                "claim": 200,
                "checkpoint": 300,
                "knowledge_query": 500,
                "assurance_compile": 600,
                "assurance_reconcile": 900,
                "assurance_resolve": 400,
                "assurance_stale_recalculation": 400,
            }
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "fixture": "synthetic Python source repository; actual process execution, no mocked services",
                "files": count,
                "entities": len(plane.store.list("entity")),
                "measurements": results,
                "targets_ms": limits,
                "targets_met": {
                    key: results[key]["median_ms"] < limit for key, limit in limits.items()
                },
                "verification": {
                    "status": proof["status"],
                    "exit_codes": [e["exit_code"] for e in proof["evidence"]],
                },
                "task_state": completed["state"],
                "assurance": {
                    "obligations": len(assurance_state["obligations"]),
                    "required": assurance_state["required"],
                    "proof_debt_after_edit": assurance_state["proof_debt"],
                    "decision_after_edit": assurance_state["decision"]["decision"],
                    "meaning": "the completed task loses its proof the moment its source moves",
                },
                "context_bytes": context["audit"]["bytes"],
                "audit": plane.store.audit(),
            }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", type=int, default=1000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.files <= 10000:
        parser.error("--files must be 1..10000")
    report = run(args.files)
    output = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    print(output, end="")
    return (
        0
        if all(report["targets_met"].values()) and report["verification"]["status"] == "PASS"
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
