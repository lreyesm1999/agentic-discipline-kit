from __future__ import annotations

import hashlib
from pathlib import Path


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_hashes(project_root: Path, paths: list[str]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    root = project_root.resolve()
    for relative in paths:
        path = (root / relative).resolve()
        if path.is_file() and path.is_relative_to(root):
            result.append({"path": path.relative_to(root).as_posix(), "sha256": hash_file(path)})
    return result
