"""A mutation shard mutates its own files, and a pull request mutates only its diff."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCOPE_SCRIPT = next(
    parent / "scripts" / "mutation_scope.py"
    for parent in Path(__file__).resolve().parents
    if (parent / "scripts" / "mutation_scope.py").is_file()
)
SCOPE = __import__("runpy").run_path(str(SCOPE_SCRIPT))


def _tree(root: Path) -> None:
    files = {
        "src/agentic_discipline/__init__.py": "",
        "src/agentic_discipline/cli.py": "def command():\n    return 1\n",
        "src/agentic_discipline/control/__init__.py": "",
        "src/agentic_discipline/control/api.py": "def assurance():\n    return 1\n",
        "src/agentic_discipline/control/assurance/__init__.py": "",
        "src/agentic_discipline/control/assurance/service.py": "def integrity():\n    return 1\n",
        "src/agentic_discipline/verifier/__init__.py": "",
        "src/agentic_discipline/verifier/executor.py": "def execute():\n    return 1\n",
        "pyproject.toml": (
            "[tool.mutmut]\n"
            'source_paths = ["src/agentic_discipline/"]\n'
            'pytest_add_cli_args_test_selection = ["tests/"]\n'
            "mutate_only_covered_lines = true\n"
        ),
        "policies/mutation-exceptions.json": json.dumps(
            {
                "exceptions": [
                    {
                        "function": "agentic_discipline.control.api.x_assurance",
                        "original": "left",
                        "mutant": "right",
                        "family": "falsy-default",
                        "reason": "only tested for truth",
                    }
                ]
            }
        ),
        "tests/control/test_service.py": (
            "from agentic_discipline.control.assurance.service import integrity\n"
        ),
        "tests/control/test_package.py": "import agentic_discipline.control.assurance\n",
    }
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def test_shards_do_not_share_a_source_file(tmp_path: Path) -> None:
    _tree(tmp_path)
    owned = {
        name: SCOPE["select"](tmp_path, name, None) for name, _prefix in SCOPE["SHARDS"]
    }
    assert owned["assurance"] == [
        "src/agentic_discipline/control/assurance/__init__.py",
        "src/agentic_discipline/control/assurance/service.py",
    ]
    assert owned["control"] == [
        "src/agentic_discipline/control/__init__.py",
        "src/agentic_discipline/control/api.py",
    ]
    assert owned["verifier"] == [
        "src/agentic_discipline/verifier/__init__.py",
        "src/agentic_discipline/verifier/executor.py",
    ]
    assert owned["core"] == [
        "src/agentic_discipline/__init__.py",
        "src/agentic_discipline/cli.py",
    ]
    flat = [path for paths in owned.values() for path in paths]
    assert len(flat) == len(set(flat)) == len(SCOPE["package_files"](tmp_path))


def test_a_pull_request_mutates_the_diff_and_what_its_tests_import(tmp_path: Path) -> None:
    _tree(tmp_path)
    changed = [
        "src/agentic_discipline/cli.py",
        "tests/control/test_service.py",
        "policies/mutation-exceptions.json",
    ]
    assert SCOPE["select"](tmp_path, "core", changed) == ["src/agentic_discipline/cli.py"]
    assert SCOPE["select"](tmp_path, "assurance", changed) == [
        "src/agentic_discipline/control/assurance/service.py"
    ]
    assert SCOPE["select"](tmp_path, "control", changed) == [
        "src/agentic_discipline/control/api.py"
    ]
    assert SCOPE["select"](tmp_path, "verifier", changed) == []


def test_only_exceptions_inside_a_diff_hunk_pull_their_source_file(tmp_path: Path) -> None:
    _tree(tmp_path)
    diff = "\n".join(
        [
            "@@ -1,2 +1,6 @@",
            '     "function": "agentic_discipline.cli.x_main",',
            '+    "function": "agentic_discipline.control.api.x_assurance",',
        ]
    )
    assert SCOPE["exception_functions_in_diff"](diff) == {
        "agentic_discipline.cli.x_main",
        "agentic_discipline.control.api.x_assurance",
    }
    assert SCOPE["select"](
        tmp_path,
        "control",
        ["policies/mutation-exceptions.json"],
        {"agentic_discipline.control.api.x_assurance"},
    ) == ["src/agentic_discipline/control/api.py"]
    assert SCOPE["select"](
        tmp_path,
        "core",
        ["policies/mutation-exceptions.json"],
        {"agentic_discipline.control.api.x_assurance"},
    ) == []


def test_importing_a_package_selects_every_module_in_it(tmp_path: Path) -> None:
    _tree(tmp_path)
    selected = SCOPE["select"](tmp_path, "assurance", ["tests/control/test_package.py"])
    assert selected == [
        "src/agentic_discipline/control/assurance/__init__.py",
        "src/agentic_discipline/control/assurance/service.py",
    ]


def test_a_workflow_only_diff_mutates_no_source(tmp_path: Path) -> None:
    _tree(tmp_path)
    assert SCOPE["select"](tmp_path, "verifier", [".github/workflows/ci.yml"]) == []


def test_the_command_restricts_mutmut_and_records_the_count(tmp_path: Path) -> None:
    _tree(tmp_path)
    output = tmp_path / "github-output.txt"
    env = {**os.environ, "GITHUB_OUTPUT": str(output)}
    completed = subprocess.run(
        [
            sys.executable,
            str(SCOPE_SCRIPT),
            "--shard",
            "assurance",
            "--event",
            "push",
            "--root",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert completed.returncode == 0, completed.stderr
    recorded = json.loads(completed.stdout)
    assert recorded["count"] == 2
    assert "only_mutate" in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert output.read_text(encoding="utf-8") == "count=2\n"
    assert (tmp_path / "mutation-scope.txt").read_text(encoding="utf-8").count("\n") == 2


def test_a_pull_request_without_a_base_is_refused(tmp_path: Path) -> None:
    _tree(tmp_path)
    completed = subprocess.run(
        [
            sys.executable,
            str(SCOPE_SCRIPT),
            "--shard",
            "core",
            "--event",
            "pull_request",
            "--root",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={key: value for key, value in os.environ.items() if key != "MUTATION_BASE"},
    )
    assert completed.returncode == 1


@pytest.mark.parametrize(
    ("path", "shard"),
    [
        ("src/agentic_discipline/control/assurance/service.py", "assurance"),
        ("src/agentic_discipline/control/api.py", "control"),
        ("src/agentic_discipline/verifier/executor.py", "verifier"),
        ("src/agentic_discipline/cli.py", "core"),
        ("tests/control/test_service.py", None),
    ],
)
def test_shard_prefixes_do_not_overlap(path: str, shard: str | None) -> None:
    assert SCOPE["shard_of"](path) == shard


def test_importing_a_submodule_does_not_expand_the_parent_package(tmp_path: Path) -> None:
    _tree(tmp_path)
    test = tmp_path / "tests/test_submodule.py"
    test.write_text("from agentic_discipline.control import api\n", encoding="utf-8")
    selected = SCOPE["select"](tmp_path, "control", ["tests/test_submodule.py"])
    assert selected == ["src/agentic_discipline/control/api.py"]


def test_restrict_mutmut_updates_pytest_test_selection(tmp_path: Path) -> None:
    _tree(tmp_path)
    pyproject = tmp_path / "pyproject.toml"
    SCOPE["restrict_mutmut"](tmp_path, ["src/agentic_discipline/control/api.py"], "control")
    text = pyproject.read_text(encoding="utf-8")
    assert 'only_mutate = [\n  "src/agentic_discipline/control/api.py",\n]' in text
    assert 'pytest_add_cli_args_test_selection = [\n  "tests/control/",\n]' in text

    # Core uses all tests/
    _tree(tmp_path)
    SCOPE["restrict_mutmut"](tmp_path, ["src/agentic_discipline/cli.py"], "core")
    core_text = (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert 'pytest_add_cli_args_test_selection = [\n  "tests/",\n]' in core_text

