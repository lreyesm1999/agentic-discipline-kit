"""Integrity audit of a diff, finding by finding.

`audit_diff` is the CI guard against weakening quality gates: skipped tests,
suppressed type checks, disabled workflows, lowered thresholds and deleted
assertions. Existing tests fed it a couple of lines, so a pattern, the per-file rules
or the exception for rewritten assertions could change unnoticed. Each case compares
the exact findings.

Sample offending lines are assembled from pieces so this file does not itself
contain the patterns the audit looks for.
"""

from __future__ import annotations

import pytest

from agentic_discipline.integrity import (
    IntegrityFinding,
    audit_diff,
    is_gate_configuration,
    is_generated_evidence,
    is_test_file,
)

SAMPLES = {
    "test_skip": "pytest" + ".skip(reason='later')",
    "coverage_ignore": "value = 1  # pragma" + ": no cover",
    "mutation_disable": "// stryker" + " disable next-line",
    "lint_disable": "/* eslint" + "-disable */",
    "type_ignore": "value = call()  # type" + ": ignore",
    "broad_swallow": "except Exception" + ": pass",
    "gate_noop": '{"command"' + ': "true"}',
}


def _diff(path: str | None, added: tuple[str, ...] = (), removed: tuple[str, ...] = ()) -> str:
    lines = [] if path is None else [f"--- a/{path}", f"+++ b/{path}", "@@ -1 +1 @@"]
    lines += [f"-{line}" for line in removed] + [f"+{line}" for line in added]
    return "\n".join(lines) + "\n"


@pytest.mark.parametrize("name", list(SAMPLES))
def test_each_weakening_pattern_in_added_lines_is_reported(name: str) -> None:
    line = SAMPLES[name]
    assert audit_diff(_diff("src/app.py", added=(line,))) == [
        IntegrityFinding("src/app.py", name, line)
    ]


def test_patterns_ignore_case_and_long_lines_are_truncated() -> None:
    upper = SAMPLES["test_skip"].upper()
    long_line = SAMPLES["lint_disable"] + " " + "x" * 600
    findings = audit_diff(_diff("src/app.py", added=(upper, long_line)))
    assert findings == [
        IntegrityFinding("src/app.py", "test_skip", upper),
        IntegrityFinding("src/app.py", "lint_disable", long_line[:500]),
    ]


def test_added_lines_before_any_file_header_have_no_file() -> None:
    line = SAMPLES["type_ignore"]
    assert audit_diff(f"+{line}\n") == [IntegrityFinding(None, "type_ignore", line)]


def test_clean_changes_and_headers_produce_no_findings() -> None:
    diff = _diff("src/app.py", added=("value = 2",), removed=("value = 1", "assert value"))
    assert audit_diff(diff) == []
    assert audit_diff("") == []


@pytest.mark.parametrize(
    ("path", "line", "name"),
    [
        ("pyproject.toml", "fail-under = 90", "threshold_change"),
        ("tox.ini", "coverage minimum 80", "threshold_change"),
        (".github/workflows/ci.yml", "    if" + ": false", "workflow_disable"),
        (".agentic/config.json", "continue-on-error" + ": true", "workflow_disable"),
    ],
)
def test_gate_configuration_changes_are_reported_only_in_gate_files(
    path: str, line: str, name: str
) -> None:
    assert audit_diff(_diff(path, added=(line,))) == [IntegrityFinding(path, name, line)]
    assert audit_diff(_diff("src/settings.py", added=(line,))) == []


def test_pattern_findings_come_before_gate_findings_on_one_line() -> None:
    line = "coverage 90 " + SAMPLES["lint_disable"]
    assert audit_diff(_diff("pytest.ini", added=(line,))) == [
        IntegrityFinding("pytest.ini", "lint_disable", line),
        IntegrityFinding("pytest.ini", "threshold_change", line),
    ]


@pytest.mark.parametrize(
    ("path", "removed", "names"),
    [
        ("tests/test_app.py", "    assert value == 1", ["assertion_removed"]),
        ("pkg/tests/test_app.py", "def test_value():", ["test_removed"]),
        (
            "tests/app.test.js",
            "  it('works', () => expect(x).toBe(1))",
            ["assertion_removed", "test_removed"],
        ),
        ("pyproject.toml", 'addopts = "--cov --cov-fail-under"', []),
        (".github/workflows/ci.yml", "      run: pytest", ["gate_removed"]),
        ("src/app.py", "assert value", []),
        ("docs/v2/evidence/tests/result.json", "assert value", []),
    ],
)
def test_removed_lines_are_judged_by_the_kind_of_file(
    path: str, removed: str, names: list[str]
) -> None:
    assert audit_diff(_diff(path, removed=(removed,))) == [
        IntegrityFinding(path, name, removed) for name in names
    ]


def test_rewritten_assertions_in_the_same_test_file_are_not_deletions() -> None:
    diff = (
        _diff("tests/test_a.py", removed=("    assert old()", "def test_gone():"))
        + _diff("tests/test_b.py", removed=("    assert other()",))
        + _diff("tests/test_a.py", added=("    assert new()",))
    )
    assert audit_diff(diff) == [
        IntegrityFinding("tests/test_a.py", "test_removed", "def test_gone():"),
        IntegrityFinding("tests/test_b.py", "assertion_removed", "    assert other()"),
    ]


def test_assertions_added_outside_tests_do_not_excuse_removals() -> None:
    diff = _diff("src/app.py", added=("assert ready",)) + _diff(
        "tests/test_app.py", removed=("    assert ready",)
    )
    assert audit_diff(diff) == [
        IntegrityFinding("tests/test_app.py", "assertion_removed", "    assert ready")
    ]


@pytest.mark.parametrize(
    ("path", "gate", "evidence", "test"),
    [
        (None, False, False, False),
        ("", False, False, False),
        ("pyproject.toml", True, False, False),
        (".coveragerc", True, False, False),
        ("sub/pyproject.toml", False, False, False),
        (".github/workflows/release.yml", True, False, False),
        (".agentic/policy.json", True, False, False),
        ("docs/v2/evidence/run.json", False, True, False),
        ("tests/test_x.py", False, False, True),
        ("src/tests/test_x.py", False, False, True),
        ("mytests/test_x.py", False, False, False),
    ],
)
def test_file_kind_helpers(path: str | None, gate: bool, evidence: bool, test: bool) -> None:
    assert (is_gate_configuration(path), is_generated_evidence(path), is_test_file(path)) == (
        gate,
        evidence,
        test,
    )


def test_gate_and_deletion_findings_are_truncated_too() -> None:
    gate_line = "coverage 90 " + "y" * 600
    removed_line = "    assert " + "z" * 600
    assert audit_diff(_diff("pytest.ini", added=(gate_line,))) == [
        IntegrityFinding("pytest.ini", "threshold_change", gate_line[:500])
    ]
    assert audit_diff(_diff("tests/test_long.py", removed=(removed_line,))) == [
        IntegrityFinding("tests/test_long.py", "assertion_removed", removed_line[:500])
    ]
