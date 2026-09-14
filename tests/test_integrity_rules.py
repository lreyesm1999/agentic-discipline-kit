"""Integrity audit rules asserted by exact findings, including where each was found."""

from __future__ import annotations

from agentic_discipline.integrity import audit_diff


def test_added_finding_records_its_file_and_line() -> None:
    findings = audit_diff("+++ b/tests/test_demo.py\n+pytest.skip('flaky')\n")
    assert [(f.file, f.pattern, f.line) for f in findings] == [
        ("tests/test_demo.py", "test_skip", "pytest.skip('flaky')")
    ]


def test_removed_finding_records_its_file_and_line() -> None:
    findings = audit_diff("+++ b/tests/test_demo.py\n-assert total == 3\n")
    assert [(f.file, f.pattern, f.line) for f in findings] == [
        ("tests/test_demo.py", "assertion_removed", "assert total == 3")
    ]


def test_added_line_before_any_file_header_has_no_file() -> None:
    findings = audit_diff("+pytest.skip('flaky')\n")
    assert [(f.file, f.pattern) for f in findings] == [(None, "test_skip")]


def test_finding_line_is_truncated_to_500_characters() -> None:
    long_skip = "pytest.skip('" + "x" * 600 + "')"
    added = audit_diff(f"+++ b/tests/test_demo.py\n+{long_skip}\n")
    removed = audit_diff("+++ b/tests/test_demo.py\n-assert " + "y" * 600 + "\n")
    assert [f.line for f in added] == [long_skip[:500]]
    assert [len(f.line) for f in removed] == [500]


def test_patterns_match_regardless_of_case() -> None:
    added = audit_diff("+++ b/src/demo.py\n+value = 1  # PRAGMA: NO COVER\n")
    gate = audit_diff("+++ b/pyproject.toml\n+FAIL-UNDER = 20\n")
    removed = audit_diff("+++ b/.github/workflows/ci.yml\n-      - name: Mutation\n")
    assert [f.pattern for f in added] == ["coverage_ignore"]
    assert [f.pattern for f in gate] == ["threshold_change"]
    assert [f.pattern for f in removed] == ["gate_removed"]


def test_context_lines_are_not_treated_as_removals() -> None:
    assert audit_diff("+++ b/tests/test_demo.py\n assert total == 3\n") == []


def test_tests_in_nested_directories_are_protected() -> None:
    diff = "+++ b/packages/api/tests/test_orders.py\n-assert order.total == 3\n"
    assert [f.pattern for f in audit_diff(diff)] == ["assertion_removed"]


def test_generated_evidence_removal_does_not_hide_later_findings() -> None:
    diff = (
        "+++ b/docs/v2/evidence/validation.json\n"
        '-  "coverage": 94\n'
        "+++ b/tests/test_demo.py\n"
        "-assert total == 3\n"
    )
    assert [(f.file, f.pattern) for f in audit_diff(diff)] == [
        ("tests/test_demo.py", "assertion_removed")
    ]
