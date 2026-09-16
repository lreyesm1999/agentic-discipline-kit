"""Report commands `crap`, `quality`, `bootstrap` and `verifier validate`.

These commands print a JSON report and return the exit code CI gates on. Existing
tests ran each with real inputs and checked the exit code, so a report field, the
artifacts location, the PASS boundary or the verifier source could change unnoticed.
Each case records the calls and compares the printed report.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline import cli


@pytest.fixture
def printed(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    output: list[Any] = []
    monkeypatch.setattr(cli, "_json", output.append)
    return output


def _args(**values: Any) -> argparse.Namespace:
    return argparse.Namespace(**values)


# --- crap -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("score", "status", "code"),
    [(7.123456, "PASS", 0), (8.0, "PASS", 0), (8.00001, "FAIL", 1)],
)
def test_crap_reports_the_rounded_score_against_the_maximum(
    monkeypatch: pytest.MonkeyPatch, printed: list[Any], score: float, status: str, code: int
) -> None:
    calls: list[tuple[float, float]] = []
    monkeypatch.setattr(cli, "crap_score", lambda c, v: calls.append((c, v)) or score)

    assert cli.command_crap(_args(complexity=5.0, coverage=60.0, max=8.0)) == code

    assert calls == [(5.0, 60.0)]
    assert printed == [
        {
            "complexity": 5.0,
            "coverage": 60.0,
            "crap": round(score, 4),
            "max": 8.0,
            "status": status,
        }
    ]


# --- quality --------------------------------------------------------------------------------


@pytest.mark.parametrize(("status", "code"), [("PASS", 0), ("FAIL", 1)])
def test_quality_writes_the_report_where_the_config_says(
    monkeypatch: pytest.MonkeyPatch,
    printed: list[Any],
    tmp_path: Path,
    status: str,
    code: int,
) -> None:
    monkeypatch.chdir(tmp_path)
    report = {"status": status, "artifacts_dir": "reports/nested", "results": []}
    configs: list[Path] = []
    monkeypatch.setattr(cli, "run_quality", lambda config: configs.append(config) or report)

    assert cli.command_quality(_args(config="agentic.config.json", artifacts=None)) == code

    assert configs == [Path("agentic.config.json")]
    written = tmp_path / "reports" / "nested" / "quality-report.json"
    assert written.read_text(encoding="utf-8") == json.dumps(report, indent=2)
    assert printed == [report]


def test_quality_artifacts_option_overrides_the_config(
    monkeypatch: pytest.MonkeyPatch, printed: list[Any], tmp_path: Path
) -> None:
    report = {"status": "PASS", "artifacts_dir": "ignored"}
    monkeypatch.setattr(cli, "run_quality", lambda config: report)
    target = tmp_path / "out"

    cli.command_quality(_args(config="c.json", artifacts=str(target)))

    assert json.loads((target / "quality-report.json").read_text(encoding="utf-8")) == report
    assert not (tmp_path / "ignored").exists()


# --- bootstrap ------------------------------------------------------------------------------


def test_bootstrap_passes_target_stack_and_force(
    monkeypatch: pytest.MonkeyPatch, printed: list[Any], tmp_path: Path
) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(
        cli,
        "bootstrap_project",
        lambda target, stack, force: calls.append((target, stack, force)) or ["WRITE a"],
    )

    assert cli.command_bootstrap(_args(target=str(tmp_path), stack="python", force=True)) == 0
    assert cli.command_bootstrap(_args(target=str(tmp_path), force=False)) == 0

    assert calls == [(tmp_path, "python", True), (tmp_path, None, False)]
    assert printed == [{"status": "PASS", "actions": ["WRITE a"]}] * 2


# --- verifier validate ----------------------------------------------------------------------


@pytest.fixture
def verifier_calls(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    seen: dict[str, Any] = {"loaded": [], "registry": [], "validated": [], "errors": []}
    monkeypatch.setattr(
        cli,
        "load_and_validate_verifier",
        lambda path: seen["loaded"].append(path) or {"id": "FROM-FILE"},
    )
    monkeypatch.setattr(
        cli,
        "load_verifier",
        lambda root, identifier: (
            seen["registry"].append((root, identifier)) or ({"id": identifier}, root / identifier)
        ),
    )

    def validate(metadata: dict[str, Any]) -> list[str]:
        seen["validated"].append(metadata)
        return list(seen["errors"])

    monkeypatch.setattr(cli, "validate_verifier", validate)
    return seen


def test_validate_a_verifier_file_by_path(
    verifier_calls: dict[str, Any], printed: list[Any], tmp_path: Path
) -> None:
    path = tmp_path / "verifier.json"
    args = _args(path=str(path), project_root=str(tmp_path), verifier_id="VER-1")
    assert cli.command_verifier_validate(args) == 0
    assert verifier_calls["loaded"] == [path]
    assert verifier_calls["registry"] == []
    assert printed == [{"status": "PASS", "errors": [], "verifier": {"id": "FROM-FILE"}}]


def test_validate_a_registered_verifier_and_report_its_errors(
    verifier_calls: dict[str, Any], printed: list[Any], tmp_path: Path
) -> None:
    verifier_calls["errors"] = ["trust: invalid"]
    args = _args(path=None, project_root=str(tmp_path), verifier_id="VER-2")
    assert cli.command_verifier_validate(args) == 1
    assert verifier_calls["registry"] == [(tmp_path, "VER-2")]
    assert verifier_calls["validated"] == [{"id": "VER-2"}]
    assert printed == [
        {"status": "FAIL", "errors": ["trust: invalid"], "verifier": {"id": "VER-2"}}
    ]


def test_quality_reuses_an_existing_artifacts_directory(
    monkeypatch: pytest.MonkeyPatch, printed: list[Any], tmp_path: Path
) -> None:
    target = tmp_path / "out"
    target.mkdir()
    monkeypatch.setattr(cli, "run_quality", lambda config: {"status": "PASS", "artifacts_dir": "x"})
    assert cli.command_quality(_args(config="c.json", artifacts=str(target))) == 0
    assert (target / "quality-report.json").is_file()
