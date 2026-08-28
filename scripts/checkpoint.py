#!/usr/bin/env python3
from __future__ import annotations

import argparse

from agentic_discipline.common import run_git

VALID = {"spec", "red", "green", "refactored", "hardened", "release"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("state", choices=sorted(VALID))
    parser.add_argument("--feature", required=True)
    args = parser.parse_args()

    tag = f"agentic/{args.feature}/{args.state}"
    run_git(["tag", "-f", tag])
    print(tag)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
