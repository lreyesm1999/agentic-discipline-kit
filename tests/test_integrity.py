from agentic_discipline.integrity import audit_diff


def test_integrity_detects_new_skip() -> None:
    diff = """+++ b/tests/test_demo.py
+pytest.skip("temporary")
"""
    findings = audit_diff(diff)
    assert findings
    assert findings[0].pattern == "test_skip"


def test_integrity_ignores_normal_code() -> None:
    diff = """+++ b/src/demo.py
+return calculate_total(items)
"""
    assert audit_diff(diff) == []


def test_integrity_flags_threshold_change_for_review() -> None:
    diff = """+++ b/pyproject.toml
+fail-under = 20
"""
    findings = audit_diff(diff)
    assert any(item.pattern == "threshold_change" for item in findings)


def test_integrity_detects_removed_assertion_and_disabled_workflow() -> None:
    diff = """+++ b/tests/test_demo.py
-assert result == 3
+++ b/.github/workflows/ci.yml
+continue-on-error: true
"""
    patterns = {finding.pattern for finding in audit_diff(diff)}
    assert "assertion_removed" in patterns
    assert "workflow_disable" in patterns
