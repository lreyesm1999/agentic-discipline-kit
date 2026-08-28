#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

EXCLUDED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
    "dist",
}


def included(path: Path) -> bool:
    if path.name in {"MANIFEST.json", ".coverage", "coverage.json", "coverage.xml"} or any(
        part in EXCLUDED_PARTS or part.endswith(".egg-info") for part in path.parts
    ):
        return False
    if path.parts and path.parts[0] in {"artifacts", ".agent-memory"}:
        return path.name == ".gitkeep"
    return path.is_file()


def main() -> int:
    root = Path.cwd()
    files = []
    for path in sorted((item for item in root.rglob("*") if included(item))):
        relative = path.relative_to(root).as_posix()
        content = path.read_bytes()
        files.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(content).hexdigest(),
                "bytes": len(content),
            }
        )
    manifest = {
        "name": "agentic-discipline-kit",
        "version": Path("VERSION").read_text(encoding="utf-8").strip(),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "files": files,
    }
    Path("MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "files": len(files)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
