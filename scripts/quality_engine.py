#!/usr/bin/env python3
"""Compatibility wrapper. Prefer the `agentic-discipline` CLI."""

import sys

from agentic_discipline.cli import main

if __name__ == "__main__":
    sys.argv.insert(1, "quality")
    main()
