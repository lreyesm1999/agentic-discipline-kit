"""Why a generated gate cannot run, reason by reason.

`init` relaxes a generated quality gate only when `_unavailable_reason` says it cannot
run here, and prints that reason to the user. The existing tests covered a missing
executable and a missing npm script, so an npx binary check, a working directory or
the "unknown must not relax" rule could change unnoticed. Each case pins the exact
reason, or that the gate stays trusted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agentic_discipline import profiles
from agentic_discipline.profiles import _unavailable_reason


@pytest.fixture
def on_path(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    looked_up: list[str] = []

    def which(name: str) -> str | None:
        looked_up.append(name)
        return None if name == "missing-tool" else f"/usr/bin/{name}"

    monkeypatch.setattr(profiles.shutil, "which", which)
    return looked_up


def _package(directory: Path, content: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "package.json").write_text(content, encoding="utf-8")


@pytest.mark.parametrize("command", [None, "", "   ", [], 42])
def test_gates_without_a_command_are_not_relaxed(
    tmp_path: Path, on_path: list[str], command: Any
) -> None:
    assert _unavailable_reason({"command": command}, tmp_path) is None
    assert on_path == []


@pytest.mark.parametrize("command", ["missing-tool --flag", ["missing-tool", "--flag"]])
def test_missing_executables_are_named(tmp_path: Path, on_path: list[str], command: Any) -> None:
    assert (
        _unavailable_reason({"command": command}, tmp_path)
        == "executable not found on PATH: missing-tool"
    )
    assert on_path == ["missing-tool"]


def test_command_items_are_converted_to_text(tmp_path: Path, on_path: list[str]) -> None:
    assert _unavailable_reason({"command": [Path("python"), "-V"]}, tmp_path) is None
    assert on_path == ["python"]


@pytest.mark.parametrize(
    ("package", "command", "reason"),
    [
        (None, "npm test", "package.json not found"),
        ("not json", "npm test", "package.json not found"),
        ('{"scripts": []}', "npm test", "package.json defines no 'test' script"),
        ('{"name": "x"}', "npm run lint", "package.json defines no 'lint' script"),
        (
            '{"scripts": {"lint": "eslint"}}',
            "npm run-script build",
            "package.json defines no 'build' script",
        ),
        ('{"scripts": {"lint": "eslint"}}', "npm run lint", None),
        ('{"scripts": {"test": "vitest"}}', "npm test", None),
        ('{"scripts": {}}', "npm run", None),
        ('{"scripts": {}}', "npm install", None),
        ('{"scripts": {}}', "npm", None),
    ],
)
def test_npm_scripts_must_exist_in_the_package_manifest(
    tmp_path: Path, on_path: list[str], package: str | None, command: str, reason: str | None
) -> None:
    if package is not None:
        _package(tmp_path, package)
    assert _unavailable_reason({"command": command}, tmp_path) == reason


def test_npm_reads_the_gates_working_directory(tmp_path: Path, on_path: list[str]) -> None:
    _package(tmp_path, '{"scripts": {}}')
    _package(tmp_path / "web", '{"scripts": {"test": "vitest"}}')
    gate = {"command": "npm test", "working_directory": "web"}
    assert _unavailable_reason(gate, tmp_path) is None
    assert _unavailable_reason({**gate, "working_directory": None}, tmp_path) == (
        "package.json defines no 'test' script"
    )
    assert _unavailable_reason({**gate, "working_directory": 7}, tmp_path) == (
        "package.json defines no 'test' script"
    )


def test_npx_binaries_are_only_judged_once_dependencies_are_installed(
    tmp_path: Path, on_path: list[str]
) -> None:
    gate = {"command": "npx eslint ."}
    assert _unavailable_reason(gate, tmp_path) is None
    (tmp_path / "node_modules" / ".bin").mkdir(parents=True)
    assert _unavailable_reason(gate, tmp_path) == "node_modules provides no 'eslint' binary"
    assert _unavailable_reason({"command": "npx"}, tmp_path) is None


@pytest.mark.parametrize("extension", ["", ".cmd", ".ps1", ".exe"])
def test_npx_accepts_every_platform_binary_name(
    tmp_path: Path, on_path: list[str], extension: str
) -> None:
    binaries = tmp_path / "web" / "node_modules" / ".bin"
    binaries.mkdir(parents=True)
    (binaries / f"eslint{extension}").write_text("", encoding="utf-8")
    gate = {"command": ["npx", "eslint"], "working_directory": "web"}
    assert _unavailable_reason(gate, tmp_path) is None
    (tmp_path / "node_modules" / ".bin").mkdir(parents=True)
    assert _unavailable_reason({"command": ["npx", "eslint"]}, tmp_path) == (
        "node_modules provides no 'eslint' binary"
    )
