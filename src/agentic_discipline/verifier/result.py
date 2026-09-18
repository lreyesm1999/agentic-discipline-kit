from __future__ import annotations

from pathlib import Path

from ..evidence import sha256_file


def artifact_hashes(project_root: Path, paths: list[str]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    root = project_root.resolve()
    for relative in paths:
        path = (root / relative).resolve()
        if path.is_file() and path.is_relative_to(root):
            result.append({"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)})
    return result
