from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .common import AgenticError
from .validation import validate_schema


class AcceptanceError(AgenticError):
    """Raised when an acceptance feature cannot produce trustworthy IR."""


def parse_feature_text(text: str, feature_id: str = "feature") -> dict[str, Any]:
    scenarios: list[dict[str, Any]] = []
    requirements: list[str] = []
    current: dict[str, Any] | None = None
    pending_id: str | None = None
    pending_tags: list[str] = []
    unsupported: list[str] = []

    for raw in text.splitlines():
        line = raw.strip()

        req_match = re.match(r"#\s*REQ:\s*(.+)", line, re.IGNORECASE)
        if req_match:
            requirements = [
                value.strip() for value in re.split(r"[,\s]+", req_match.group(1)) if value.strip()
            ]
            continue

        if line.startswith("@"):
            tags = [tag for tag in line.split() if tag.startswith("@")]
            pending_tags.extend(tag[1:] for tag in tags)
            for tag in tags:
                if re.fullmatch(r"@AC-\d+", tag, re.IGNORECASE):
                    pending_id = tag[1:].upper()
            continue

        scenario_match = re.match(r"Scenario:\s*(.+)", line, re.IGNORECASE)
        if scenario_match:
            current = {
                "id": pending_id or f"AC-{len(scenarios) + 1:03d}",
                "requirements": requirements.copy(),
                "name": scenario_match.group(1).strip(),
                "tags": pending_tags.copy(),
                "steps": [],
            }
            scenarios.append(current)
            pending_id = None
            pending_tags = []
            continue

        step_match = re.match(r"(Given|When|Then|And)\s+(.+)", line, re.IGNORECASE)
        if step_match and current is not None:
            current["steps"].append(
                {"kind": step_match.group(1).lower(), "text": step_match.group(2)}
            )

        if re.match(r"(Scenario Outline|Background|Examples|Rule|But):?\b", line, re.IGNORECASE):
            unsupported.append(line)

    result = {"feature_id": feature_id, "scenarios": scenarios}
    errors = validate_acceptance_ir(result)
    if unsupported:
        errors.append("unsupported Gherkin syntax: " + ", ".join(unsupported))
    if errors:
        raise AcceptanceError("invalid acceptance feature: " + "; ".join(errors))
    return result


def validate_acceptance_ir(result: dict[str, Any]) -> list[str]:
    errors = validate_schema(result, "acceptance-ir.schema.json")
    seen: set[str] = set()
    for index, scenario in enumerate(result.get("scenarios", [])):
        if not isinstance(scenario, dict):
            continue
        scenario_id = scenario.get("id")
        if isinstance(scenario_id, str):
            if scenario_id in seen:
                errors.append(f"scenarios.{index}.id: duplicate scenario id {scenario_id!r}")
            seen.add(scenario_id)
        if not scenario.get("requirements"):
            errors.append(f"scenarios.{index}.requirements: at least one requirement is required")
        kinds = {step.get("kind") for step in scenario.get("steps", []) if isinstance(step, dict)}
        for required_kind in ("given", "when", "then"):
            if required_kind not in kinds:
                errors.append(f"scenarios.{index}.steps: missing {required_kind} step")
    if not result.get("scenarios"):
        errors.append("scenarios: at least one scenario is required")
    return errors


def compile_feature(input_path: Path, output_path: Path) -> dict[str, Any]:
    result = parse_feature_text(input_path.read_text(encoding="utf-8"), input_path.stem)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
