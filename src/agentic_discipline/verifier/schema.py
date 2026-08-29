from __future__ import annotations

from pathlib import Path
from typing import Any

from ..common import AgenticError
from ..validation import load_json, validate_schema


def validate_verifier(metadata: dict[str, Any]) -> list[str]:
    errors = validate_schema(metadata, "verifier.schema.json")
    working_directory = metadata.get("working_directory")
    if isinstance(working_directory, str):
        path = Path(working_directory)
        if path.is_absolute() or ".." in path.parts:
            errors.append("working_directory: must stay inside the project root")
    sensitivity = metadata.get("sensitivity")
    if isinstance(sensitivity, dict) and sensitivity.get("status") == "PROVEN":
        evidence = sensitivity.get("evidence")
        if not isinstance(evidence, str) or not evidence:
            errors.append("sensitivity.evidence: required when status is PROVEN")
    if (
        metadata.get("protected") is True
        and metadata.get("sensitivity", {}).get("status") != "PROVEN"
    ):
        errors.append("protected verifiers must have PROVEN sensitivity")
    return errors


def load_and_validate_verifier(path: Path) -> dict[str, Any]:
    metadata = load_json(path, "verifier contract")
    errors = validate_verifier(metadata)
    if errors:
        raise AgenticError("invalid verifier contract: " + "; ".join(errors))
    return metadata
