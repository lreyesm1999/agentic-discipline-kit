#!/usr/bin/env python3
"""Fail release validation when mutmut's recorded survivors remain unresolved."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REQUIRED = (
    "total",
    "killed",
    "survived",
    "timeout",
    "no_tests",
    "skipped",
    "suspicious",
    "check_was_interrupted_by_user",
    "segfault",
)
UNRESOLVED = REQUIRED[2:]


def gate(report: Any) -> dict[str, Any]:
    if (
        not isinstance(report, dict)
        or set(report) != set(REQUIRED)
        or any(type(report.get(key)) is not int or report[key] < 0 for key in REQUIRED)
    ):
        return {"status": "FAIL", "reason": "Missing or invalid mutmut metrics"}
    # mutmut 3.8 omits not_checked and caught_by_type_check from its CI export.
    # Unaccounted variants fail closed until the report can explain them.
    if (
        report["total"] == 0
        or report["killed"] + sum(report[key] for key in UNRESOLVED) != report["total"]
    ):
        return {"status": "FAIL", "reason": "Incomplete or inconsistent mutation evidence"}
    remaining = {key: report[key] for key in UNRESOLVED if report[key]}
    return {
        "status": "FAIL" if remaining else "PASS",
        "total": report["total"],
        "killed": report["killed"],
        "unresolved": remaining,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = gate(json.loads(args.report.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        result = {"status": "FAIL", "reason": f"Cannot read mutation evidence: {exc}"}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
