#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from agentic_discipline.common import changed_files


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-ref", default="HEAD~1")
    args = parser.parse_args()

    files = changed_files(args.base_ref)
    production = [
        item
        for item in files
        if not any(token in item.lower() for token in ("test", "spec", "acceptance", "docs/"))
    ]
    tests = [
        item
        for item in files
        if any(token in item.lower() for token in ("test", "spec", "acceptance"))
    ]
    modules = sorted({item.split("/")[0] if "/" in item else "." for item in production})
    print(
        json.dumps(
            {
                "changed_files": files,
                "production_files": production,
                "test_files": tests,
                "top_level_modules": modules,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
