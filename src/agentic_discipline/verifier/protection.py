from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from ..common import AgenticError
from ..evidence import sha256_file
from .registry import _write_registry, load_registry
from .schema import load_and_validate_verifier


def check_protected_verifiers(project_root: Path) -> list[str]:
    registry = load_registry(project_root)
    findings: list[str] = []
    for entry in registry["verifiers"]:
        if entry["trust"] != "PROTECTED":
            continue
        metadata = (project_root / entry["path"] / "verifier.json").resolve()
        if not metadata.is_file():
            findings.append(f"protected verifier missing: {entry['id']}")
        elif entry.get("metadata_sha256") and sha256_file(metadata) != entry["metadata_sha256"]:
            findings.append(f"protected verifier changed: {entry['id']}")
    return findings


def protect_verifier(project_root: Path, verifier_id: str) -> dict[str, Any]:
    registry = load_registry(project_root)
    for entry in registry["verifiers"]:
        if entry["id"] == verifier_id:
            metadata = (project_root / entry["path"] / "verifier.json").resolve()
            if not metadata.is_file():
                raise AgenticError(f"verifier metadata not found: {verifier_id}")
            contract = load_and_validate_verifier(metadata)
            if contract["sensitivity"]["status"] != "PROVEN":
                raise AgenticError("only sensitivity-validated verifiers can be protected")
            entry["trust"] = "PROTECTED"
            entry["metadata_sha256"] = sha256_file(metadata)
            _write_registry(project_root, registry)
            return cast(dict[str, Any], entry)
    raise AgenticError(f"verifier not found: {verifier_id}")
