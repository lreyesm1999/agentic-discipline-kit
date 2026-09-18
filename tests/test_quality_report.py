"""Quality report assembly, gate by gate.

`run_quality` runs every configured gate from the right directory and decides the
overall status CI reports. Existing tests ran real gates and checked the status, so
a working directory could be ignored, an optional failure could fail the report, or
the report defaults could change unnoticed. Gate execution is recorded here so each
case pins exactly what `run_quality` asks for and returns.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline import quality
from agentic_discipline.quality import GateResult, run_quality


def _result(name: str, required: bool, status: str) -> GateResult:
    return GateResult(
        name=name,
        required=required,
        command=["tool", name],
        exit_code=0 if status == "PASS" else 1,
        status=status,
        duration_seconds=0.1,
        metrics={},
        threshold_failures=[],
        stdout="",
        stderr="",
    )


@pytest.fixture
def gates(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    seen: dict[str, Any] = {"calls": [], "statuses": {}}

    def run_gate(gate: dict[str, Any], cwd: Path | None = None) -> GateResult:
        seen["calls"].append((gate["name"], cwd))
        return _result(gate["name"], gate.get("required", True), seen["statuses"][gate["name"]])

    monkeypatch.setattr(quality, "run_gate", run_gate)
    return seen


def _config(directory: Path, **extra: Any) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "agentic.config.json"
    path.write_text(
        json.dumps(
            {
                "gates": [
                    {"name": "lint", "command": ["ruff", "check"], "required": True},
                    {
                        "name": "web",
                        "command": ["npm", "test"],
                        "required": True,
                        "working_directory": "web",
                    },
                    {"name": "docs", "command": ["mkdocs", "build"], "required": False},
                ],
                **extra,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_gates_run_from_the_config_directory_and_report_in_order(
    gates: dict[str, Any], tmp_path: Path
) -> None:
    config = _config(tmp_path / "repo", project="demo", artifacts_dir="out")
    gates["statuses"] = {"lint": "PASS", "web": "PASS", "docs": "FAIL"}
    root = config.resolve().parent

    report = run_quality(config)

    assert gates["calls"] == [("lint", root / "."), ("web", root / "web"), ("docs", root / ".")]
    assert report == {
        "project": "demo",
        "artifacts_dir": "out",
        "status": "PASS",
        "results": [
            asdict(_result("lint", True, "PASS")),
            asdict(_result("web", True, "PASS")),
            asdict(_result("docs", False, "FAIL")),
        ],
    }


def test_an_explicit_working_root_overrides_the_config_directory(
    gates: dict[str, Any], tmp_path: Path
) -> None:
    config = _config(tmp_path / "config", project="demo")
    gates["statuses"] = {"lint": "PASS", "web": "PASS", "docs": "PASS"}
    checkout = tmp_path / "checkout"

    run_quality(config, cwd=checkout)

    root = checkout.resolve()
    assert gates["calls"] == [("lint", root / "."), ("web", root / "web"), ("docs", root / ".")]


@pytest.mark.parametrize("failing", ["FAIL", "ERROR"])
def test_a_required_gate_that_does_not_pass_fails_the_report(
    gates: dict[str, Any], tmp_path: Path, failing: str
) -> None:
    config = _config(tmp_path, project="demo")
    gates["statuses"] = {"lint": "PASS", "web": failing, "docs": "PASS"}
    assert run_quality(config)["status"] == "FAIL"


def test_artifacts_directory_defaults_when_the_config_omits_it(
    gates: dict[str, Any], tmp_path: Path
) -> None:
    # The schema requires "project", so only the artifacts directory can default.
    config = _config(tmp_path, project="demo")
    gates["statuses"] = {"lint": "PASS", "web": "PASS", "docs": "PASS"}
    report = run_quality(config)
    assert (report["project"], report["artifacts_dir"], report["status"]) == (
        "demo",
        "artifacts",
        "PASS",
    )
