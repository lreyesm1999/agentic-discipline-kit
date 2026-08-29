from __future__ import annotations

import json
import math
import re
import shlex
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .validation import load_quality_config


@dataclass
class GateResult:
    name: str
    required: bool
    command: str | list[str]
    exit_code: int
    status: str
    duration_seconds: float
    metrics: dict[str, float | str]
    threshold_failures: list[str]
    stdout: str
    stderr: str
    error: str | None = None


def extract_metrics(text: str, parser: dict[str, Any] | None) -> dict[str, float | str]:
    if not parser:
        return {}

    if parser.get("type") == "regex":
        metrics: dict[str, float | str] = {}
        for name, pattern in parser.get("metrics", {}).items():
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                value = match.group(1)
                try:
                    metrics[name] = float(value)
                except ValueError:
                    metrics[name] = value
        return metrics

    if parser.get("type") == "json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return {}
        metrics = {}
        for name, dotted_path in parser.get("metrics", {}).items():
            current: Any = data
            try:
                for part in dotted_path.split("."):
                    current = current[int(part)] if isinstance(current, list) else current[part]
                metrics[name] = current
            except (KeyError, IndexError, TypeError, ValueError):
                continue
        return metrics

    return {}


def evaluate_thresholds(
    metrics: dict[str, float | str], thresholds: dict[str, dict[str, float]]
) -> list[str]:
    failures: list[str] = []
    for metric, rule in thresholds.items():
        if metric not in metrics:
            failures.append(f"{metric}=UNKNOWN")
            continue
        try:
            value = float(metrics[metric])
        except (TypeError, ValueError):
            failures.append(f"{metric}=INVALID")
            continue
        if not math.isfinite(value):
            failures.append(f"{metric}=INVALID")
            continue
        if "min" in rule and value < rule["min"]:
            failures.append(f"{metric} {value} < {rule['min']}")
        if "max" in rule and value > rule["max"]:
            failures.append(f"{metric} {value} > {rule['max']}")
        if "eq" in rule and value != rule["eq"]:
            failures.append(f"{metric} {value} != {rule['eq']}")
    return failures


def run_gate(gate: dict[str, Any], cwd: Path | None = None) -> GateResult:
    start = time.monotonic()
    configured_command = gate["command"]
    command = (
        shlex.split(configured_command, posix=True)
        if isinstance(configured_command, str)
        else configured_command
    )
    try:
        process = subprocess.run(
            command,
            cwd=cwd,
            shell=False,
            text=True,
            capture_output=True,
            check=False,
            timeout=float(gate.get("timeout_seconds", 900)),
        )
    except subprocess.TimeoutExpired as exc:
        stdout = (
            exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else exc.stdout
        )
        stderr = (
            exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else exc.stderr
        )
        return GateResult(
            name=gate["name"],
            required=gate.get("required", True),
            command=configured_command,
            exit_code=124,
            status="ERROR",
            duration_seconds=round(time.monotonic() - start, 3),
            metrics={},
            threshold_failures=[],
            stdout=(stdout or "")[-20_000:],
            stderr=(stderr or "")[-20_000:],
            error=f"gate timed out after {gate.get('timeout_seconds', 900)} seconds",
        )
    except OSError as exc:
        return GateResult(
            name=gate["name"],
            required=gate.get("required", True),
            command=configured_command,
            exit_code=127,
            status="ERROR",
            duration_seconds=round(time.monotonic() - start, 3),
            metrics={},
            threshold_failures=[],
            stdout="",
            stderr="",
            error=str(exc),
        )
    combined = f"{process.stdout}\n{process.stderr}"
    metrics = extract_metrics(combined, gate.get("parser"))
    threshold_failures = evaluate_thresholds(metrics, gate.get("thresholds", {}))
    passed = process.returncode == 0 and not threshold_failures

    return GateResult(
        name=gate["name"],
        required=gate.get("required", True),
        command=configured_command,
        exit_code=process.returncode,
        status="PASS" if passed else "FAIL",
        duration_seconds=round(time.monotonic() - start, 3),
        metrics=metrics,
        threshold_failures=threshold_failures,
        stdout=process.stdout[-20_000:],
        stderr=process.stderr[-20_000:],
    )


def run_quality(config_path: Path, cwd: Path | None = None) -> dict[str, Any]:
    config = load_quality_config(config_path)
    project_root = cwd.resolve() if cwd is not None else config_path.resolve().parent
    results = [
        run_gate(gate, cwd=project_root / gate.get("working_directory", "."))
        for gate in config["gates"]
    ]
    failed = [item for item in results if item.required and item.status != "PASS"]
    return {
        "project": config.get("project", "unknown"),
        "artifacts_dir": config.get("artifacts_dir", "artifacts"),
        "status": "PASS" if not failed else "FAIL",
        "results": [asdict(item) for item in results],
    }
