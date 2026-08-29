from __future__ import annotations

from pathlib import Path
from typing import Any

from ..common import AgenticError


def sensitivity_status(metadata: dict[str, Any], project_root: Path, directory: Path) -> str:
    sensitivity = metadata.get("sensitivity", {})
    if sensitivity.get("status") != "PROVEN":
        return "DRAFT"
    evidence = sensitivity.get("evidence")
    if not isinstance(evidence, str) or not evidence:
        raise AgenticError("validated verifier is missing sensitivity evidence")
    evidence_path = (project_root / evidence).resolve()
    if not evidence_path.is_relative_to(project_root.resolve()) or not evidence_path.is_file():
        evidence_path = (directory / evidence).resolve()
    if not evidence_path.is_file():
        raise AgenticError(f"sensitivity evidence not found: {evidence}")
    return "VALIDATED"
