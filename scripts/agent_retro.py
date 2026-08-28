#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feature", required=True)
    parser.add_argument("--pattern", required=True)
    parser.add_argument("--cause", required=True)
    parser.add_argument("--rule", required=True)
    parser.add_argument("--evidence", default="")
    args = parser.parse_args()

    target = Path(".agent-memory/failures.jsonl")
    target.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "feature": args.feature,
        "pattern": args.pattern,
        "cause": args.cause,
        "candidate_rule": args.rule,
        "evidence": args.evidence,
    }
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
