from __future__ import annotations

import json
import math
import re
import sys
import sysconfig
from importlib import resources
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from jsonschema import Draft202012Validator

from .common import AgenticError


class ValidationError(AgenticError):
    """Raised when an Agentic Discipline document is structurally invalid."""


def _schema_candidates(name: str) -> list[Path]:
    candidates = [Path.cwd() / "schemas" / name]
    # Mutation runners and source checkouts may relocate this module below the
    # repository root. Search all ancestors instead of assuming one fixed depth.
    candidates.extend(parent / "schemas" / name for parent in Path(__file__).resolve().parents)
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        candidates.insert(0, Path(frozen_root) / "schemas" / name)
    candidates.append(
        Path(sysconfig.get_path("data")) / "share" / "agentic-discipline" / "schemas" / name
    )
    try:
        packaged = resources.files("agentic_discipline") / "schemas" / name
        if packaged.is_file():
            candidates.insert(0, Path(str(packaged)))
    except (ModuleNotFoundError, TypeError):
        pass
    return candidates


def load_json(path: Path, label: str = "JSON document") -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValidationError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(
            f"{label} is invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    if not isinstance(data, dict):
        raise ValidationError(f"{label} must be a JSON object")
    return data


def load_schema(name: str) -> dict[str, Any]:
    for candidate in _schema_candidates(name):
        if candidate.is_file():
            return load_json(candidate, f"schema {name}")
    raise ValidationError(f"schema not found: {name}")


def validate_schema(data: dict[str, Any], schema_name: str) -> list[str]:
    validator = Draft202012Validator(load_schema(schema_name))
    errors: list[str] = []
    for error in sorted(validator.iter_errors(data), key=lambda item: list(item.path)):
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        errors.append(f"{location}: {error.message}")
    return errors


def validate_quality_config(config: dict[str, Any]) -> list[str]:
    errors = validate_schema(config, "agentic-config.schema.json")
    gates = config.get("gates")
    if not isinstance(gates, list):
        return errors

    names: set[str] = set()
    required_count = 0
    for index, gate in enumerate(gates):
        if not isinstance(gate, dict):
            continue
        name = gate.get("name")
        if isinstance(name, str):
            if name in names:
                errors.append(f"gates.{index}.name: duplicate gate name {name!r}")
            names.add(name)
        if gate.get("required", True) is True:
            required_count += 1

        working_directory = gate.get("working_directory")
        if isinstance(working_directory, str):
            posix_path = PurePosixPath(working_directory)
            windows_path = PureWindowsPath(working_directory)
            if (
                posix_path.is_absolute()
                or windows_path.is_absolute()
                or ".." in posix_path.parts
                or ".." in windows_path.parts
            ):
                errors.append(f"gates.{index}.working_directory: must stay inside the project root")

        parser = gate.get("parser")
        thresholds = gate.get("thresholds", {})
        declared_metrics = set(parser.get("metrics", {})) if isinstance(parser, dict) else set()
        if isinstance(parser, dict) and parser.get("type") == "regex":
            for metric, pattern in parser.get("metrics", {}).items():
                try:
                    re.compile(pattern)
                except (re.error, TypeError) as exc:
                    errors.append(f"gates.{index}.parser.metrics.{metric}: invalid regex: {exc}")
        if isinstance(thresholds, dict):
            for metric, rules in thresholds.items():
                if metric not in declared_metrics:
                    errors.append(
                        f"gates.{index}.thresholds.{metric}: metric is not declared by the parser"
                    )
                if isinstance(rules, dict):
                    for operator, value in rules.items():
                        if isinstance(value, (int, float)) and not math.isfinite(float(value)):
                            errors.append(
                                f"gates.{index}.thresholds.{metric}.{operator}: value must be finite"
                            )

    if gates and required_count == 0:
        errors.append("gates: at least one gate must be required")
    return errors


def load_quality_config(path: Path) -> dict[str, Any]:
    config = load_json(path, "quality configuration")
    errors = validate_quality_config(config)
    if errors:
        raise ValidationError("invalid quality configuration: " + "; ".join(errors))
    return config
