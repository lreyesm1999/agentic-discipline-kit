"""The install helpers create every missing directory above what they write.

`init` happens to call them in an order where each parent already exists, so a
helper that stopped creating intermediate directories would go unnoticed until a
caller wrote somewhere deeper. Each case writes two or more levels below an
existing directory.
"""

from __future__ import annotations

import json
from pathlib import Path

from agentic_discipline.bootstrap import _copy_item, _install_payload, _write_json


def test_copying_a_file_creates_its_missing_parents(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("x\n", encoding="utf-8")
    target = tmp_path / "a" / "b" / "c.txt"

    _copy_item(source, target, force=False, actions=[])

    assert target.read_text(encoding="utf-8") == "x\n"


def test_copying_a_directory_creates_its_missing_parents(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "f.txt").write_text("x\n", encoding="utf-8")
    target = tmp_path / "a" / "b" / "copy"

    _copy_item(source, target, force=False, actions=[])

    assert (target / "f.txt").is_file()


def test_writing_json_creates_its_missing_parents(tmp_path: Path) -> None:
    path = tmp_path / "a" / "b" / "c.json"

    _write_json(path, {"k": 1}, force=False, actions=[], dry_run=False)

    assert json.loads(path.read_text(encoding="utf-8")) == {"k": 1}


def test_the_verification_directories_are_created_without_any_payload(tmp_path: Path) -> None:
    empty_kit = tmp_path / "kit"
    empty_kit.mkdir()
    target = tmp_path / "project"
    target.mkdir()

    _install_payload(empty_kit, target, force=False, actions=[], dry_run=False)

    for name in ("generated", "artifacts"):
        assert (target / ".agentic" / "verification" / name).is_dir()
