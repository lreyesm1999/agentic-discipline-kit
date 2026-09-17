"""CI gate commands, decision by decision.

`graph`, `integrity`, `protected` and `verify` are the commands CI runs to block a
change. Existing tests ran each once with real inputs, so an option could stop
reaching the validator, a protected prefix could stop matching, a verifier status
could be summarized wrongly, or an exit code could flip without failing. Each case
records what the command asks for and what it prints and returns.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline import cli
from agentic_discipline.common import AgenticError
from agentic_discipline.integrity import IntegrityAudit


@pytest.fixture
def printed(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    output: list[Any] = []
    monkeypatch.setattr(cli, "_json", output.append)
    return output


def _args(**values: Any) -> argparse.Namespace:
    return argparse.Namespace(**values)


def _failing(*_: Any, **__: Any) -> Any:
    raise AgenticError("git is unavailable")


# --- graph ----------------------------------------------------------------------------------


@pytest.fixture
def graph_calls(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    seen: dict[str, Any] = {"validate": [], "issues": [], "orphans": []}
    monkeypatch.setattr(cli, "load_json", lambda path, label: {"path": path, "label": label})

    def validate(graph: Any, base_path: Any = None, complete: bool = False) -> list[str]:
        seen["validate"].append((graph, base_path, complete))
        return list(seen["issues"])

    monkeypatch.setattr(cli, "validate_requirement_graph", validate)
    monkeypatch.setattr(cli, "orphan_requirements", lambda graph: list(seen["orphans"]))
    seen["path"] = tmp_path / "graphs" / "feature.json"
    return seen


def test_graph_passes_its_options_to_the_validator(
    graph_calls: dict[str, Any], printed: list[Any]
) -> None:
    path = graph_calls["path"]
    graph = {"path": path, "label": "requirement graph"}

    assert cli.command_graph(_args(graph=str(path))) == 0
    assert cli.command_graph(_args(graph=str(path), check_paths=True, complete=True)) == 0
    assert cli.command_graph(_args(graph=str(path), check_paths=False, complete=False)) == 0

    assert graph_calls["validate"] == [
        (graph, None, False),
        (graph, path.parent, True),
        (graph, None, False),
    ]
    assert printed == [{"issues": [], "orphans": [], "status": "PASS"}] * 3


@pytest.mark.parametrize(
    ("issues", "orphans"), [(["edges.0: bad"], []), ([], ["FR-2"]), (["x"], ["FR-2"])]
)
def test_graph_fails_on_issues_or_orphans(
    graph_calls: dict[str, Any], printed: list[Any], issues: list[str], orphans: list[str]
) -> None:
    graph_calls["issues"], graph_calls["orphans"] = issues, orphans
    assert cli.command_graph(_args(graph=str(graph_calls["path"]))) == 1
    assert printed == [{"issues": issues, "orphans": orphans, "status": "FAIL"}]


# --- integrity ------------------------------------------------------------------------------


def test_integrity_combines_diff_and_protected_verifier_findings(
    monkeypatch: pytest.MonkeyPatch, printed: list[Any], tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    git_calls: list[list[str]] = []
    roots: list[Path] = []
    monkeypatch.setattr(cli, "run_git", lambda arguments: git_calls.append(arguments) or "DIFF")
    diff_finding = cli.IntegrityFinding("src/x.py", "sample_rule", "+value = 1")
    retired = cli.IntegrityFinding("tests/test_x.py", "test_removed", "def test_x():")
    audited: list[Any] = []

    def audit(diff: str, still_defined: Any) -> IntegrityAudit:
        audited.append((diff, still_defined))
        return IntegrityAudit(findings=[diff_finding], retired=[retired])

    monkeypatch.setattr(cli, "audit_changes", audit)
    monkeypatch.setattr(
        cli, "check_protected_verifiers", lambda root: roots.append(root) or ["VER-1 changed"]
    )

    assert cli.command_integrity(_args(base_ref="origin/main")) == 1

    assert git_calls == [["diff", "--unified=0", "origin/main", "--"]]
    assert audited == [("DIFF", cli._defined_in_repository)]
    assert roots == [tmp_path]
    assert printed == [
        {
            "status": "FAIL",
            "findings": [
                diff_finding,
                cli.IntegrityFinding(None, "protected_verifier", "VER-1 changed"),
            ],
            "retired_tests": [retired],
        }
    ]


def test_integrity_passes_without_findings(
    monkeypatch: pytest.MonkeyPatch, printed: list[Any]
) -> None:
    monkeypatch.setattr(cli, "run_git", lambda arguments: "")
    monkeypatch.setattr(
        cli, "audit_changes", lambda diff, still_defined: IntegrityAudit(findings=[], retired=[])
    )
    monkeypatch.setattr(cli, "check_protected_verifiers", lambda root: [])
    assert cli.command_integrity(_args(base_ref="main")) == 0
    assert printed == [{"status": "PASS", "findings": [], "retired_tests": []}]


def test_retired_tests_alone_do_not_fail_the_audit(
    monkeypatch: pytest.MonkeyPatch, printed: list[Any]
) -> None:
    retired = cli.IntegrityFinding("tests/test_x.py", "test_removed", "def test_x():")
    monkeypatch.setattr(cli, "run_git", lambda arguments: "")
    monkeypatch.setattr(
        cli,
        "audit_changes",
        lambda diff, still_defined: IntegrityAudit(findings=[], retired=[retired]),
    )
    monkeypatch.setattr(cli, "check_protected_verifiers", lambda root: [])
    assert cli.command_integrity(_args(base_ref="main")) == 0
    assert printed == [{"status": "PASS", "findings": [], "retired_tests": [retired]}]


@pytest.mark.parametrize(
    ("command", "patched"),
    [("command_integrity", "run_git"), ("command_protected", "changed_files")],
)
def test_git_failures_exit_2_with_the_error_on_stderr(
    monkeypatch: pytest.MonkeyPatch,
    printed: list[Any],
    capsys: pytest.CaptureFixture[str],
    command: str,
    patched: str,
) -> None:
    monkeypatch.setattr(cli, patched, _failing)
    assert getattr(cli, command)(_args(base_ref="main")) == 2
    assert capsys.readouterr().err == "git is unavailable\n"
    assert printed == []


# --- protected ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        ".agentic/config.json",
        "specs/feature.md",
        "acceptance/checkout.feature",
        "architecture/adr-1.md",
        "policies/review.md",
        "schemas/task.schema.json",
        "skills/demo/SKILL.md",
        ".github/workflows/ci.yml",
        "AGENTS.md",
        "MASTER_PROMPT.md",
        "agentic.config.json",
        ".github\\workflows\\ci.yml",
    ],
)
def test_each_protected_location_fails_the_check(
    monkeypatch: pytest.MonkeyPatch, printed: list[Any], path: str
) -> None:
    monkeypatch.setattr(cli, "changed_files", lambda ref: ["src/app.py", path])
    assert cli.command_protected(_args(base_ref="main")) == 1
    assert printed == [{"status": "FAIL", "changed": [path.replace("\\", "/")]}]


def test_unprotected_changes_pass_and_protected_order_is_kept(
    monkeypatch: pytest.MonkeyPatch, printed: list[Any]
) -> None:
    unprotected = [
        "src/app.py",
        "docs/AGENTS.md",
        "specsheet.md",
        ".agentic",
        ".github/other.yml",
        "agentic.config.json.bak",
    ]
    monkeypatch.setattr(cli, "changed_files", lambda ref: unprotected)
    assert cli.command_protected(_args(base_ref="main")) == 0
    assert printed == [{"status": "PASS", "changed": []}]

    monkeypatch.setattr(cli, "changed_files", lambda ref: ["specs/b.md", "src/x.py", "AGENTS.md"])
    assert cli.command_protected(_args(base_ref="main")) == 1
    assert printed[-1] == {"status": "FAIL", "changed": ["specs/b.md", "AGENTS.md"]}


# --- verify ---------------------------------------------------------------------------------


@pytest.fixture
def verifiers(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    seen: dict[str, Any] = {"listed": [], "executed": [], "registry": [], "statuses": {}}

    def list_verifiers(root: Path) -> list[dict[str, str]]:
        seen["listed"].append(root)
        return [{"id": identifier} for identifier in seen["registry"]]

    def execute(root: Path, identifier: str) -> dict[str, str]:
        seen["executed"].append((root, identifier))
        return {"id": identifier, "status": seen["statuses"][identifier]}

    monkeypatch.setattr(cli, "list_verifiers", list_verifiers)
    monkeypatch.setattr(cli, "execute_verifier", execute)
    return seen


def test_verify_without_verifiers_is_not_applicable(
    verifiers: dict[str, Any], printed: list[Any], tmp_path: Path
) -> None:
    assert cli.command_verify(_args(project_root=str(tmp_path), verifier_id=None)) == 0
    assert printed == [{"status": "NOT_APPLICABLE", "results": []}]
    assert (verifiers["listed"], verifiers["executed"]) == ([tmp_path.resolve()], [])


def test_verify_a_single_verifier_skips_the_registry(
    verifiers: dict[str, Any], printed: list[Any], tmp_path: Path
) -> None:
    verifiers["statuses"] = {"VER-2": "PASS"}
    assert cli.command_verify(_args(project_root=str(tmp_path), verifier_id="VER-2")) == 0
    assert verifiers["listed"] == []
    assert verifiers["executed"] == [(tmp_path.resolve(), "VER-2")]
    assert printed == [{"status": "PASS", "results": [{"id": "VER-2", "status": "PASS"}]}]


@pytest.mark.parametrize(
    ("statuses", "summary", "code"),
    [
        (["PASS", "PASS"], "PASS", 0),
        (["PASS", "FAIL"], "FAIL", 1),
        (["FAIL", "BLOCKED"], "BLOCKED", 1),
        (["BLOCKED", "PASS"], "BLOCKED", 1),
        (["ERROR"], "FAIL", 1),
    ],
)
def test_verify_summarizes_every_registered_verifier(
    verifiers: dict[str, Any],
    printed: list[Any],
    tmp_path: Path,
    statuses: list[str],
    summary: str,
    code: int,
) -> None:
    identifiers = [f"VER-{index}" for index in range(len(statuses))]
    verifiers["registry"] = identifiers
    verifiers["statuses"] = dict(zip(identifiers, statuses, strict=True))

    assert cli.command_verify(_args(project_root=str(tmp_path), verifier_id=None)) == code

    assert verifiers["executed"] == [(tmp_path.resolve(), i) for i in identifiers]
    assert printed == [
        {
            "status": summary,
            "results": [{"id": i, "status": s} for i, s in zip(identifiers, statuses, strict=True)],
        }
    ]
