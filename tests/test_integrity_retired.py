"""Retired tests: a test removed together with the code it exercised.

The audit reported every removed test and assertion as weakened verification, so a
change that deleted a feature and its tests could never pass, however legitimate.
A test whose code no longer exists cannot run, so removing it weakens nothing. The
audit now lists such a test as retired instead of failing on it, and only when the
same change deletes that code and nothing in the repository defines it any more.
Each case pins where that exception applies and where it must not.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import pytest

from agentic_discipline import cli
from agentic_discipline.integrity import IntegrityAudit, IntegrityFinding, audit_changes, audit_diff

TEST_DEF = "def test_alias_still_works():"
ALIAS_ASSERT = "    assert alias(1) == 1"


def _file(path: str, removed: tuple[str, ...] = (), added: tuple[str, ...] = ()) -> str:
    lines = [f"--- a/{path}", f"+++ b/{path}", "@@ -1 +1 @@"]
    lines += [f"-{line}" for line in removed] + [f"+{line}" for line in added]
    return "\n".join(lines) + "\n"


def _deleted(path: str, removed: tuple[str, ...]) -> str:
    lines = [f"--- a/{path}", "+++ /dev/null", "@@ -1 +0,0 @@"]
    return "\n".join(lines + [f"-{line}" for line in removed]) + "\n"


def _gone(name: str) -> bool:
    return False


def _removed_test(*body: str) -> str:
    return _file("tests/test_alias.py", removed=(TEST_DEF, *body))


def _removed_alias(path: str = "src/app.py") -> str:
    return _file(path, removed=("def alias(value):", "    return value"))


TEST_FINDING = IntegrityFinding("tests/test_alias.py", "test_removed", TEST_DEF)
ASSERT_FINDING = IntegrityFinding("tests/test_alias.py", "assertion_removed", ALIAS_ASSERT)


def test_a_test_removed_with_the_code_it_called_is_retired() -> None:
    diff = _removed_alias() + _removed_test(ALIAS_ASSERT)

    assert audit_changes(diff, still_defined=_gone) == IntegrityAudit(
        findings=[], retired=[TEST_FINDING, ASSERT_FINDING]
    )


def test_order_of_the_files_in_the_diff_does_not_matter() -> None:
    diff = _removed_test(ALIAS_ASSERT) + _removed_alias()

    assert audit_changes(diff, still_defined=_gone).retired == [TEST_FINDING, ASSERT_FINDING]


def test_code_still_defined_elsewhere_keeps_the_removal_a_finding() -> None:
    asked: list[str] = []

    def defined(name: str) -> bool:
        asked.append(name)
        return True

    diff = _removed_alias() + _removed_test(ALIAS_ASSERT, "    assert alias(2) == 2")

    audit = audit_changes(diff, still_defined=defined)

    assert audit.retired == []
    assert [finding.pattern for finding in audit.findings] == [
        "test_removed",
        "assertion_removed",
        "assertion_removed",
    ]
    # The repository is asked once per name, however many lines call it.
    assert asked == ["alias"]


def test_code_redefined_in_the_same_change_keeps_the_removal_a_finding() -> None:
    def never_asked(name: str) -> bool:
        raise AssertionError(f"asked about {name}")

    diff = (
        _removed_alias()
        + _file("src/other.py", added=("def alias(value):",))
        + _removed_test(ALIAS_ASSERT)
    )

    assert audit_changes(diff, still_defined=never_asked) == IntegrityAudit(
        findings=[TEST_FINDING, ASSERT_FINDING], retired=[]
    )


def test_a_test_that_also_lost_a_check_of_living_code_is_not_retired() -> None:
    living = "    assert other(1) == 1"
    diff = _removed_alias() + _removed_test(ALIAS_ASSERT, living)

    assert audit_changes(diff, still_defined=_gone) == IntegrityAudit(
        findings=[
            TEST_FINDING,
            IntegrityFinding("tests/test_alias.py", "assertion_removed", living),
        ],
        retired=[ASSERT_FINDING],
    )


def test_a_removed_test_without_assertions_is_not_retired() -> None:
    diff = _removed_alias() + _removed_test("    alias(1)")

    assert audit_changes(diff, still_defined=_gone) == IntegrityAudit(
        findings=[TEST_FINDING], retired=[]
    )


def test_a_name_mentioned_without_being_called_does_not_retire() -> None:
    mention = "    assert alias is not None"
    diff = _removed_alias() + _removed_test(mention)

    assert audit_changes(diff, still_defined=_gone).retired == []


def test_deleting_a_test_helper_does_not_retire_the_tests_using_it() -> None:
    diff = _removed_alias("tests/helpers.py") + _removed_test(ALIAS_ASSERT)

    assert audit_changes(diff, still_defined=_gone) == IntegrityAudit(
        findings=[TEST_FINDING, ASSERT_FINDING], retired=[]
    )


def test_each_removed_test_is_judged_by_its_own_assertions() -> None:
    second = "def test_other_still_works():"
    living = "    assert other(1) == 1"
    diff = _removed_alias() + _removed_test(ALIAS_ASSERT, "", second, living)

    audit = audit_changes(diff, still_defined=_gone)

    assert audit.retired == [TEST_FINDING, ASSERT_FINDING]
    assert audit.findings == [
        IntegrityFinding("tests/test_alias.py", "test_removed", second),
        IntegrityFinding("tests/test_alias.py", "assertion_removed", living),
    ]


def test_assertions_removed_elsewhere_are_not_the_body_of_a_removed_test() -> None:
    # A kept line ends the removed block, so a later hunk's assertion is not part of it.
    diff = _removed_alias() + (
        "--- a/tests/test_alias.py\n+++ b/tests/test_alias.py\n@@ -1 +1 @@\n"
        f"-{TEST_DEF}\n-    alias(1)\n@@ -9 +8 @@\n-{ALIAS_ASSERT}\n"
    )

    assert audit_changes(diff, still_defined=_gone) == IntegrityAudit(
        findings=[TEST_FINDING], retired=[ASSERT_FINDING]
    )


def test_a_removed_block_ends_where_the_next_file_begins() -> None:
    diff = (
        _removed_alias()
        + _file("tests/test_alias.py", removed=(TEST_DEF,))
        + _file("tests/test_more.py", removed=(ALIAS_ASSERT,))
    )

    assert audit_changes(diff, still_defined=_gone) == IntegrityAudit(
        findings=[TEST_FINDING],
        retired=[IntegrityFinding("tests/test_more.py", "assertion_removed", ALIAS_ASSERT)],
    )


@pytest.mark.parametrize(
    "definition",
    ["class alias:", "function alias(value) {", "export async function alias(value) {"],
)
def test_classes_and_javascript_functions_count_as_deleted_code(definition: str) -> None:
    diff = _file("src/app.js", removed=(definition,)) + _removed_test(ALIAS_ASSERT)

    assert audit_changes(diff, still_defined=_gone).retired == [TEST_FINDING, ASSERT_FINDING]


def test_other_findings_are_never_retired() -> None:
    gate = "      run: alias(1)"
    diff = _removed_alias() + _file(".github/workflows/ci.yml", removed=(gate,))

    assert audit_changes(diff, still_defined=_gone) == IntegrityAudit(
        findings=[IntegrityFinding(".github/workflows/ci.yml", "gate_removed", gate)], retired=[]
    )


def test_audit_diff_alone_never_retires_a_test() -> None:
    diff = _removed_alias() + _removed_test(ALIAS_ASSERT)

    assert audit_diff(diff) == [TEST_FINDING, ASSERT_FINDING]


def test_assertions_of_a_deleted_test_file_are_attributed_to_that_file() -> None:
    # A deleted file's header is `+++ /dev/null`; its lines used to be charged to
    # whichever file preceded it, so a deleted test file after a source file was
    # not audited at all.
    diff = _file("src/app.py", added=("value = 1",)) + _deleted(
        "tests/test_gone.py", ("def test_gone():", "    assert value == 1")
    )

    assert audit_diff(diff) == [
        IntegrityFinding("tests/test_gone.py", "test_removed", "def test_gone():"),
        IntegrityFinding("tests/test_gone.py", "assertion_removed", "    assert value == 1"),
    ]


def test_a_dev_null_line_without_an_old_path_keeps_the_current_file() -> None:
    diff = _file("tests/test_a.py", removed=(ALIAS_ASSERT,)) + "+++ /dev/null\n-assert x\n"

    assert [finding.file for finding in audit_diff(diff)] == ["tests/test_a.py"] * 2


def test_the_command_passes_and_lists_retired_tests(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    asked: list[str] = []
    diff = _removed_alias() + _removed_test(ALIAS_ASSERT)
    monkeypatch.setattr(cli, "run_git", lambda arguments: diff)
    monkeypatch.setattr(cli, "check_protected_verifiers", lambda root: [])
    monkeypatch.setattr(cli, "_defined_in_repository", lambda name: asked.append(name) or False)

    assert cli.command_integrity(argparse.Namespace(base_ref="origin/main")) == 0

    assert asked == ["alias"]
    assert json.loads(capsys.readouterr().out) == {
        "status": "PASS",
        "findings": [],
        "retired_tests": [
            {"file": "tests/test_alias.py", "pattern": "test_removed", "line": TEST_DEF},
            {"file": "tests/test_alias.py", "pattern": "assertion_removed", "line": ALIAS_ASSERT},
        ],
    }


def test_the_command_fails_on_findings_and_still_lists_retired_tests(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    living = "    assert other(1) == 1"
    diff = _removed_alias() + _removed_test(ALIAS_ASSERT, living)
    monkeypatch.setattr(cli, "run_git", lambda arguments: diff)
    monkeypatch.setattr(cli, "check_protected_verifiers", lambda root: [])
    monkeypatch.setattr(cli, "_defined_in_repository", lambda name: False)

    assert cli.command_integrity(argparse.Namespace(base_ref="origin/main")) == 1

    printed = json.loads(capsys.readouterr().out)
    assert printed["status"] == "FAIL"
    assert [finding["line"] for finding in printed["findings"]] == [TEST_DEF, living]
    assert [finding["line"] for finding in printed["retired_tests"]] == [ALIAS_ASSERT]


def _hunk(path: str, *lines: str) -> str:
    """A file section whose lines already carry their `+`, `-` or context prefix."""

    return "\n".join([f"--- a/{path}", f"+++ b/{path}", "@@ -1 +1 @@", *lines]) + "\n"


def test_a_diff_that_starts_with_a_deleted_file_header_is_read() -> None:
    assert audit_diff("\n".join(["+++ /dev/null", "-assert value"]) + "\n") == []


def test_a_removed_test_ends_where_its_hunk_ends() -> None:
    # The next hunk's removal is not part of the test, so it cannot stop it being retired.
    diff = _removed_alias() + _hunk(
        "tests/test_alias.py", f"-{TEST_DEF}", f"-{ALIAS_ASSERT}", "@@ -9 +8 @@", "-    unused = 1"
    )

    assert audit_changes(diff, still_defined=_gone) == IntegrityAudit(
        findings=[], retired=[TEST_FINDING, ASSERT_FINDING]
    )


def test_removed_assertions_are_recognised_in_any_letter_case() -> None:
    line = "    Expect(total).toBe(3)"

    assert audit_diff(_file("tests/app.test.js", removed=(line,))) == [
        IntegrityFinding("tests/app.test.js", "assertion_removed", line)
    ]


def test_file_headers_are_not_read_as_added_or_removed_lines() -> None:
    # Each path would match a pattern if its header were audited as content.
    diff = (
        _file(".github/workflows/mutation-2.yml", added=("name: build",))
        + _file("tests/test_a.py", added=("value = 1",))
        + _file("tests/assert/test_b.py", added=("other = 2",))
    )

    assert audit_diff(diff) == []


def test_a_removed_assertion_in_a_path_named_assert_is_still_reported() -> None:
    diff = _file("tests/assert/test_b.py", removed=(ALIAS_ASSERT,))

    assert audit_diff(diff) == [
        IntegrityFinding("tests/assert/test_b.py", "assertion_removed", ALIAS_ASSERT)
    ]


def test_unchanged_context_lines_are_neither_removed_code_nor_removed_tests() -> None:
    diff = _hunk("src/app.py", " def alias(value):", "-    old = 1") + _hunk(
        "tests/test_alias.py", f" {TEST_DEF}", f" {ALIAS_ASSERT}", "-    unused = 1"
    )

    assert audit_changes(diff, still_defined=_gone) == IntegrityAudit(findings=[], retired=[])


def test_generated_evidence_does_not_stop_the_audit_of_later_lines() -> None:
    diff = _file("docs/v2/evidence/result.json", removed=("assert value",)) + _removed_test(
        ALIAS_ASSERT
    )

    assert audit_diff(diff) == [TEST_FINDING, ASSERT_FINDING]


def test_only_an_added_assertion_excuses_a_removed_one_in_the_same_file() -> None:
    removed = "    assert total() == 3"
    diff = _file("tests/test_a.py", removed=(removed,), added=("    total()",))

    assert audit_diff(diff) == [IntegrityFinding("tests/test_a.py", "assertion_removed", removed)]


def test_gate_words_removed_outside_gate_configuration_are_not_reported() -> None:
    assert audit_diff(_file("src/app.py", removed=("    run(command)",))) == []


def _git(root: Path, *arguments: str) -> None:
    subprocess.run(["git", *arguments], cwd=root, check=True, capture_output=True)


def test_the_repository_check_finds_definitions_in_tracked_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _git(tmp_path, "init", "-q")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "app.py").write_text(
        "def kept(value):\n    return value\n\nclass Model:\n    pass\n", encoding="utf-8"
    )
    (tmp_path / "web.js").write_text("export function render() {}\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("kept_elsewhere(1) is only mentioned\n", encoding="utf-8")
    (tmp_path / "untracked.py").write_text("def untracked():\n    pass\n", encoding="utf-8")
    _git(tmp_path, "add", "pkg/app.py", "web.js", "notes.md")
    monkeypatch.chdir(tmp_path / "pkg")

    assert cli._defined_in_repository("kept")
    assert cli._defined_in_repository("Model")
    assert cli._defined_in_repository("render")
    assert not cli._defined_in_repository("kept_elsewhere")
    assert not cli._defined_in_repository("untracked")
    # A longer name that starts with the one asked about is a different definition.
    assert not cli._defined_in_repository("kep")


def test_the_repository_check_assumes_defined_when_git_cannot_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)

    assert cli._defined_in_repository("anything")
    # Git's complaint must not reach the terminal: the audit prints JSON other tools read.
    assert capfd.readouterr() == ("", "")
