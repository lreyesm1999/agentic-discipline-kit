from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

from agentic_discipline import cli
from agentic_discipline.common import AgenticError


def ns(**values: object) -> argparse.Namespace:
    return argparse.Namespace(**values)


def test_doctor_passes_from_repository_root() -> None:
    assert cli.command_doctor(ns()) == 0


def test_crap_command_pass_and_fail() -> None:
    assert cli.command_crap(ns(complexity=7.0, coverage=92.0, max=8.0)) == 0
    assert cli.command_crap(ns(complexity=10.0, coverage=0.0, max=8.0)) == 1


def test_acceptance_command(tmp_path: Path) -> None:
    source = tmp_path / "demo.feature"
    target = tmp_path / "demo.json"
    source.write_text(
        "# REQ: FR-001\n@AC-001\nScenario: demo\nGiven x\nWhen y\nThen z\n",
        encoding="utf-8",
    )
    assert cli.command_acceptance(ns(input=str(source), output=str(target))) == 0
    assert json.loads(target.read_text(encoding="utf-8"))["scenarios"][0]["id"] == "AC-001"


def test_init_command_reports_detected_profile(tmp_path: Path) -> None:
    target = tmp_path / "project"
    target.mkdir()
    (target / "package.json").write_text("{}", encoding="utf-8")

    assert (
        cli.command_init(
            ns(
                target=str(target),
                profile=[],
                profile_file=[],
                force=False,
                max_depth=4,
            )
        )
        == 0
    )


def test_bootstrap_command_remains_usable_without_stack(tmp_path: Path) -> None:
    target = tmp_path / "project"

    assert cli.command_bootstrap(ns(target=str(target), stack=None, force=False)) == 0


def test_graph_command_pass_and_fail(tmp_path: Path) -> None:
    good = tmp_path / "good.json"
    good.write_text(
        json.dumps(
            {
                "feature_id": "FEAT-001",
                "nodes": [
                    {"id": "FR-001", "type": "requirement"},
                    {"id": "AC-001", "type": "acceptance"},
                ],
                "edges": [{"from": "FR-001", "to": "AC-001", "relation": "verified_by"}],
            }
        ),
        encoding="utf-8",
    )
    assert cli.command_graph(ns(graph=str(good))) == 0

    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {
                "feature_id": "FEAT-001",
                "nodes": [{"id": "FR-001", "type": "requirement"}],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )
    assert cli.command_graph(ns(graph=str(bad))) == 1


def test_risk_command_success_and_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "changed_files", lambda _ref: ["src/payment.py"])
    monkeypatch.setattr(cli, "run_git", lambda _args: "+ payment balance")
    assert cli.command_risk(ns(base_ref="main")) == 0

    def fail(_ref: str) -> list[str]:
        raise AgenticError("bad git")

    monkeypatch.setattr(cli, "changed_files", fail)
    assert cli.command_risk(ns(base_ref="main")) == 2


def test_integrity_command_pass_fail_and_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "run_git", lambda _args: "+++ b/src/x.py\n+return 1")
    assert cli.command_integrity(ns(base_ref="main")) == 0

    monkeypatch.setattr(
        cli,
        "run_git",
        lambda _args: '+++ b/tests/x.py\n+pytest.skip("temporary")',
    )
    assert cli.command_integrity(ns(base_ref="main")) == 1

    def fail(_args: list[str]) -> str:
        raise AgenticError("bad git")

    monkeypatch.setattr(cli, "run_git", fail)
    assert cli.command_integrity(ns(base_ref="main")) == 2


def test_protected_command_pass_fail_and_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "changed_files", lambda _ref: ["src/x.py"])
    assert cli.command_protected(ns(base_ref="main")) == 0

    monkeypatch.setattr(cli, "changed_files", lambda _ref: ["policies/security.md"])
    assert cli.command_protected(ns(base_ref="main")) == 1

    def fail(_ref: str) -> list[str]:
        raise AgenticError("bad git")

    monkeypatch.setattr(cli, "changed_files", fail)
    assert cli.command_protected(ns(base_ref="main")) == 2


def test_quality_command_writes_report(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    config.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cli, "run_quality", lambda _path: {"status": "PASS", "results": []})
    assert cli.command_quality(ns(config=str(config), artifacts=str(tmp_path / "artifacts"))) == 0
    assert (tmp_path / "artifacts" / "quality-report.json").exists()

    monkeypatch.setattr(cli, "run_quality", lambda _path: {"status": "FAIL", "results": []})
    assert cli.command_quality(ns(config=str(config), artifacts=str(tmp_path / "artifacts2"))) == 1


def test_evidence_command(tmp_path: Path) -> None:
    artifact = tmp_path / "report.json"
    artifact.write_text('{"status":"PASS"}', encoding="utf-8")
    ledger = tmp_path / "ledger.jsonl"
    assert (
        cli.command_evidence(
            ns(
                artifact=str(artifact),
                ledger=str(ledger),
                tool="pytest",
                executed_command="pytest",
                exit_code=0,
            )
        )
        == 0
    )
    assert ledger.exists()


def test_parser_and_main(monkeypatch: pytest.MonkeyPatch) -> None:
    parser = cli.build_parser()
    parsed = parser.parse_args(["crap", "--complexity", "7", "--coverage", "92"])
    assert parsed.command == "crap"
    initialized = parser.parse_args(["init"])
    assert initialized.target == "."
    assert initialized.profile == []

    monkeypatch.setattr(
        sys,
        "argv",
        ["agentic-discipline", "crap", "--complexity", "7", "--coverage", "92"],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 0
