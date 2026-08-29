from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from ..common import AgenticError
from ..validation import load_json, validate_schema
from .schema import load_and_validate_verifier


def verification_root(project_root: Path) -> Path:
    return project_root.resolve() / ".agentic" / "verification"


def registry_path(project_root: Path) -> Path:
    return verification_root(project_root) / "registry.json"


def _default_registry() -> dict[str, Any]:
    return {"schema_version": "1", "verifiers": []}


def load_registry(project_root: Path) -> dict[str, Any]:
    path = registry_path(project_root)
    if not path.exists():
        return _default_registry()
    registry = load_json(path, "verifier registry")
    errors = validate_schema(registry, "verifier-registry.schema.json")
    if errors:
        raise AgenticError("invalid verifier registry: " + "; ".join(errors))
    return registry


def _write_registry(project_root: Path, registry: dict[str, Any]) -> None:
    path = registry_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")


def _metadata_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def list_verifiers(project_root: Path) -> list[dict[str, Any]]:
    return list(load_registry(project_root)["verifiers"])


def _resolve_entry(project_root: Path, verifier_id: str) -> tuple[dict[str, Any], Path]:
    for entry in list_verifiers(project_root):
        if entry["id"] == verifier_id:
            path = (project_root.resolve() / entry["path"]).resolve()
            if not path.is_relative_to(project_root.resolve()):
                raise AgenticError(f"verifier path escapes project root: {entry['path']}")
            return entry, path
    raise AgenticError(f"verifier not found: {verifier_id}")


def load_verifier(project_root: Path, verifier_id: str) -> tuple[dict[str, Any], Path]:
    entry, directory = _resolve_entry(project_root, verifier_id)
    metadata_path = directory / "verifier.json"
    if entry.get("trust") == "PROTECTED" and entry.get("metadata_sha256"):
        actual = _metadata_hash(metadata_path) if metadata_path.is_file() else None
        if actual != entry["metadata_sha256"]:
            raise AgenticError(f"protected verifier changed: {verifier_id}")
    metadata = load_and_validate_verifier(metadata_path)
    if metadata["id"] != verifier_id:
        raise AgenticError(f"verifier id mismatch: registry={verifier_id}, metadata={metadata['id']}")
    return metadata, directory


def register_verifier(source: Path, project_root: Path) -> dict[str, Any]:
    source = source.resolve()
    source_dir = source if source.is_dir() else source.parent
    metadata_path = source_dir / "verifier.json"
    metadata = load_and_validate_verifier(metadata_path)
    destination = verification_root(project_root) / "generated" / metadata["id"]
    if destination.exists():
        raise AgenticError(f"verifier already registered: {metadata['id']}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, destination)
    registry = load_registry(project_root)
    if any(item["id"] == metadata["id"] for item in registry["verifiers"]):
        shutil.rmtree(destination)
        raise AgenticError(f"verifier already registered: {metadata['id']}")
    registry["verifiers"].append(
        {
            "id": metadata["id"],
            "path": destination.relative_to(project_root.resolve()).as_posix(),
            "trust": "VALIDATED" if metadata["sensitivity"]["status"] == "PROVEN" else "DRAFT",
            "persistence": metadata["persistence"],
            "last_validation": datetime.now(timezone.utc).isoformat() if metadata["sensitivity"]["status"] == "PROVEN" else None,
            "metadata_sha256": _metadata_hash(destination / "verifier.json"),
        }
    )
    _write_registry(project_root, registry)
    return cast(dict[str, Any], registry["verifiers"][-1])
