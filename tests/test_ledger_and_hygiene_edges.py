"""The ledger names what it cannot find; hygiene reads only the lines a diff added.

`verify_ledger` with artifact checks must say which record lost its artifact, not
just fail. `_added_blocks` groups added lines, and the `+++` header that opens every
file in a diff is not one of them.
"""

from __future__ import annotations

import json
from pathlib import Path

from agentic_discipline.evidence import append_evidence, verify_ledger
from agentic_discipline.evolution import _added_blocks, lifecycle_path, register_lifecycle


def test_a_missing_artifact_is_named_by_record(tmp_path: Path) -> None:
    artifact = tmp_path / "report.json"
    artifact.write_text("{}", encoding="utf-8")
    ledger = tmp_path / "ledger.jsonl"
    append_evidence(ledger, artifact, tool="pytest", command="pytest", exit_code=0)
    artifact.unlink()

    result = verify_ledger(ledger, check_artifacts=True)

    assert result["status"] == "FAIL"
    assert result["errors"] == [f"record 1: artifact not found: {artifact.resolve()}"]


def test_the_file_header_of_a_diff_is_not_an_added_line() -> None:
    diff = "--- a/app.py\n+++ b/app.py\n@@ -1 +1,2 @@\n+first\n+second\n context\n+third\n"

    assert _added_blocks(diff) == [["first", "second"], ["third"]]


def test_the_lifecycle_registry_is_written_indented_for_review(tmp_path: Path) -> None:
    item = {"id": "TMP-1", "path": "scratch.py", "state": "TEMPORARY"}

    register_lifecycle(tmp_path, item)

    expected = {"schema_version": "1", "artifacts": [item]}
    written = lifecycle_path(tmp_path).read_bytes().decode("utf-8").replace("\r\n", "\n")
    assert written == json.dumps(expected, indent=2) + "\n"
