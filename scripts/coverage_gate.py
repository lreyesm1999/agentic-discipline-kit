#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def percentage(covered: int, total: int) -> float:
    return 100.0 if total == 0 else covered / total * 100.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Enforce separate line and branch coverage gates.")
    parser.add_argument("--report", default="coverage.json")
    parser.add_argument("--min-line", type=float, default=90.0)
    parser.add_argument("--min-branch", type=float, default=85.0)
    args = parser.parse_args()

    data = json.loads(Path(args.report).read_text(encoding="utf-8"))
    totals = data["totals"]
    line = percentage(totals["covered_lines"], totals["num_statements"])
    branch = percentage(totals["covered_branches"], totals["num_branches"])
    failures = []
    if line < args.min_line:
        failures.append(f"line_coverage {line:.2f} < {args.min_line:.2f}")
    if branch < args.min_branch:
        failures.append(f"branch_coverage {branch:.2f} < {args.min_branch:.2f}")
    result = {
        "status": "FAIL" if failures else "PASS",
        "line_coverage": round(line, 2),
        "branch_coverage": round(branch, 2),
        "threshold_failures": failures,
    }
    print(json.dumps(result, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
