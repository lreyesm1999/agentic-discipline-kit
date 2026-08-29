#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from agentic_discipline.bootstrap import bootstrap_project


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bootstrap Agentic Discipline contracts into another repository."
    )
    parser.add_argument("--target", required=True, help="Target repository path")
    parser.add_argument(
        "--stack",
        help="Optional legacy profile override; omitted means automatic detection",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing Agentic Discipline files",
    )
    args = parser.parse_args()

    for action in bootstrap_project(Path(args.target), args.stack, args.force):
        print(action)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
