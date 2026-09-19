"""Text with accents survives on a platform whose default encoding is not UTF-8.

Every file the kit reads or writes that can hold free text, and every subprocess it
reads as text, names UTF-8 explicitly. On Linux dropping that argument changes
nothing, so the mutation run could not tell; on Windows it garbles or refuses
non-ASCII text. `use_legacy_code_page` makes an unspecified encoding mean cp1252
here too, and each case round-trips text that cp1252 and UTF-8 encode differently.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from legacy_code_page import use_legacy_code_page

from agentic_discipline.acceptance import compile_feature
from agentic_discipline.adapters import MANAGED_END, MANAGED_START, Emission
from agentic_discipline.bootstrap import _update_gitignore
from agentic_discipline.common import run_git
from agentic_discipline.control.cli import read_input
from agentic_discipline.control.discovery import git, scan
from agentic_discipline.profiles import _load_json, _package_scripts
from agentic_discipline.quality import run_gate
from agentic_discipline.skills import load_discipline
from agentic_discipline.validation import load_json

TEXT = "Café — naïve 中文"


@pytest.fixture(autouse=True)
def legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    use_legacy_code_page(monkeypatch)


def _text(path: Path) -> str:
    """The file decoded as UTF-8, with Windows line endings normalized."""
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n")


def _utf8(path: Path, text: str) -> Path:
    path.write_bytes(text.encode("utf-8"))
    return path


def test_the_simulation_garbles_text_read_without_an_encoding(tmp_path: Path) -> None:
    # Guard for the cases below: without an encoding the text must not survive.
    path = _utf8(tmp_path / "x.txt", TEXT)
    assert path.read_text() != TEXT


def test_a_feature_with_accents_compiles(tmp_path: Path) -> None:
    feature = _utf8(
        tmp_path / "orders.feature",
        "# REQ: FR-1\nFeature: Orders\n  Scenario: Café paid\n"
        "    Given a cart\n    When it is paid\n    Then an order exists\n",
    )

    result = compile_feature(feature, tmp_path / "out.json")

    assert result["scenarios"][0]["name"] == "Café paid"


def test_generated_files_are_written_and_compared_as_utf8(tmp_path: Path) -> None:
    path = tmp_path / "rule.md"
    emission = Emission()

    emission.write(path, TEXT + "\n")
    emission.write(path, TEXT + "\n")

    assert _text(path) == TEXT + "\n"
    assert [action.split(" ", 1)[0] for action in emission.actions] == ["WRITE", "SKIP"]


def test_user_text_around_the_managed_region_is_kept(tmp_path: Path) -> None:
    path = _utf8(tmp_path / "AGENTS.md", f"{TEXT}\n\n{MANAGED_START}\nold\n{MANAGED_END}\n")

    Emission().write_managed(path, "new")

    assert _text(path).startswith(TEXT + "\n\n")


def test_a_gitignore_with_accents_is_extended_not_garbled(tmp_path: Path) -> None:
    _utf8(tmp_path / ".gitignore", "cafés/\n")

    _update_gitignore(tmp_path, [], dry_run=False)

    assert _text(tmp_path / ".gitignore").startswith("cafés/\n")


def test_json_documents_with_accents_are_read_as_utf8(tmp_path: Path) -> None:
    raw = json.dumps({"label": TEXT, "scripts": {"test": TEXT}}, ensure_ascii=False)
    path = _utf8(tmp_path / "doc.json", raw)
    _utf8(tmp_path / "package.json", raw)

    assert read_input(path)["label"] == TEXT
    assert load_json(path)["label"] == TEXT
    assert _load_json(path, "profile")["label"] == TEXT
    assert _package_scripts(tmp_path) == {"test": TEXT}


def test_a_discipline_with_accents_loads_its_text(tmp_path: Path) -> None:
    path = _utf8(
        tmp_path / "SKILL.md",
        "---\nname: agentic-x\ndescription: Café rules\nwhen_to_use: always\n"
        "id: x\ntitle: X\nsummary: Café\n---\n\n" + TEXT + "\n",
    )

    discipline = load_discipline(path)

    assert TEXT in discipline.body


def test_source_with_accents_is_scanned_as_written(tmp_path: Path) -> None:
    _utf8(tmp_path / "app.py", f"def café():\n    return '{TEXT}'\n")

    (item,) = [f for f in scan(tmp_path)["files"] if f["path"] == "app.py"]

    assert [s["name"] for s in item["symbols"]] == ["café"]
    assert TEXT in item["excerpt"]


def test_subprocess_output_with_accents_is_read_as_utf8(tmp_path: Path) -> None:
    run_git(["init", "-q"], cwd=tmp_path)
    _utf8(tmp_path / "notes.txt", TEXT + "\n")
    run_git(["add", "notes.txt"], cwd=tmp_path)

    assert f"+{TEXT}" in run_git(["diff", "--cached"], cwd=tmp_path)
    assert TEXT in git(tmp_path, ["diff", "--cached"])
    printing = f"import sys; sys.stdout.buffer.write({(TEXT + chr(10)).encode()!r})"
    assert (
        run_gate({"name": "t", "command": [sys.executable, "-c", printing]}).stdout == TEXT + "\n"
    )
