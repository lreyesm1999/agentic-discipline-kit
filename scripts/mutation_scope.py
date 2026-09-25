#!/usr/bin/env python3
"""Choose the source files one mutation shard will mutate, and tell mutmut.

The campaign is four shards, so each job mutates a different part of the package:

- assurance: ``src/agentic_discipline/control/assurance/``
- control: the rest of ``src/agentic_discipline/control/``
- verifier: ``src/agentic_discipline/verifier/``
- core: every other module under ``src/agentic_discipline/``

On a pull request the shard mutates only what that diff can affect: a changed source
file, a module imported by a changed test, and a module named by a changed entry in
``policies/mutation-exceptions.json``. Pushing to main, or running the workflow by
hand, mutates the shard's whole tree. The diff is compared with the base branch, so
a later commit does not drop a file the pull request still changes.

The selected paths are written to ``mutation-scope.txt`` and to ``tool.mutmut.only_mutate``,
which mutmut reads from ``pyproject.toml``. ``count`` is appended to ``GITHUB_OUTPUT``
when that file is set, so the workflow can skip mutmut when the shard has nothing to do.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SHARDS: tuple[tuple[str, str], ...] = (
    ("assurance", "src/agentic_discipline/control/assurance/"),
    ("verifier", "src/agentic_discipline/verifier/"),
    ("control", "src/agentic_discipline/control/"),
    ("core", "src/agentic_discipline/"),
)
MUTMUT_MARKER = "mutate_only_covered_lines = true\n"
TEST_SELECTION_MARKER = 'pytest_add_cli_args_test_selection = ["tests/"]\n'
SHARD_TEST_SELECTION: dict[str, list[str]] = {
    "assurance": ["tests/control/"],
    "control": ["tests/control/"],
    "verifier": [
        "tests/verifier/",
        "tests/test_verifier.py",
        "tests/test_verifier_contract_rules.py",
        "tests/test_verifier_execution_paths.py",
        "tests/test_verifier_registration.py",
        "tests/test_verifier_result_contract.py",
        "tests/control/test_verifier_inputs.py",
    ],
    "core": ["tests/"],
}


def shard_of(path: str) -> str | None:
    """The shard that owns a source file. More specific prefixes are listed first."""

    normalized = path.replace("\\", "/")
    for name, prefix in SHARDS:
        if normalized.startswith(prefix):
            return name
    return None


def package_files(root: Path) -> list[str]:
    base = root / "src" / "agentic_discipline"
    return sorted(
        path.relative_to(root).as_posix()
        for path in base.rglob("*.py")
        if path.is_file()
    )


def files_for_module(root: Path, module: str) -> set[str]:
    """The source file a module names, or every file of a package imported as a whole."""

    parts = module.split(".")
    if not parts or parts[0] != "agentic_discipline":
        return set()
    for end in range(len(parts), 0, -1):
        candidate = root.joinpath("src", *parts[:end])
        file = candidate.with_suffix(".py")
        if file.is_file():
            return {file.relative_to(root).as_posix()}
        if (candidate / "__init__.py").is_file():
            if end == len(parts):
                return {
                    path.relative_to(root).as_posix() for path in candidate.rglob("*.py") if path.is_file()
                }
            return {(candidate / "__init__.py").relative_to(root).as_posix()}
    return set()


def modules_imported_by(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return {
        name
        for name in found
        if name == "agentic_discipline" or name.startswith("agentic_discipline.")
    }


def files_from_exceptions(path: Path) -> set[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("exceptions", [])
    if not isinstance(entries, list):
        raise ValueError("exceptions file must hold an exceptions list")
    files: set[str] = set()
    for entry in entries:
        function = entry.get("function", "") if isinstance(entry, dict) else ""
        module = function.rpartition(".")[0]
        if module.startswith("agentic_discipline"):
            files.add("src/" + module.replace(".", "/") + ".py")
    return files


def exception_functions_in_diff(diff: str) -> set[str]:
    """Functions named inside a hunk of the exceptions file, changed or only sitting beside one."""

    functions: set[str] = set()
    in_hunk = False
    for line in diff.splitlines():
        if line.startswith("@@"):
            in_hunk = True
            continue
        if not in_hunk or line.startswith(("diff ", "index ", "---", "+++")):
            continue
        match = re.search(r'"function":\s*"([^"]+)"', line)
        if match:
            functions.add(match.group(1))
    return functions


def affected_files(
    root: Path, changed: list[str], exception_functions: set[str] | None = None
) -> set[str]:
    """Source files a diff can affect."""

    selected: set[str] = set()
    for relative in changed:
        path = relative.replace("\\", "/")
        if path.startswith("src/agentic_discipline/") and path.endswith(".py"):
            selected.add(path)
        elif path.startswith("tests/") and path.endswith(".py"):
            test = root / path
            if not test.is_file():
                continue
            for module in modules_imported_by(test):
                selected.update(files_for_module(root, module))
        elif path == "policies/mutation-exceptions.json" and (root / path).is_file():
            if not exception_functions:
                selected.update(files_from_exceptions(root / path))
            else:
                for function in exception_functions:
                    module = function.rpartition(".")[0]
                    if module.startswith("agentic_discipline"):
                        selected.add("src/" + module.replace(".", "/") + ".py")
    return {path for path in selected if (root / path).is_file()}


def select(
    root: Path,
    shard: str,
    changed: list[str] | None,
    exception_functions: set[str] | None = None,
) -> list[str]:
    """Files in one shard. ``changed is None`` mutates the shard's whole tree."""

    owned = [path for path in package_files(root) if shard_of(path) == shard]
    if changed is None:
        return owned
    affected = affected_files(root, changed, exception_functions)
    return [path for path in owned if path in affected]


def _git_diff(base: str, *paths: str) -> str:
    completed = subprocess.run(
        ["git", "diff", "-U8", "--diff-filter=ACMR", f"{base}...HEAD", "--", *paths],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "git diff failed"
        raise SystemExit(message)
    return completed.stdout


def changed_files(base: str) -> list[str]:
    # --name-only cannot be combined with a unified diff, so the name list is its own call.
    completed = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", f"{base}...HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "git diff failed"
        raise SystemExit(message)
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def restrict_mutmut(root: Path, files: list[str], shard: str | None = None) -> None:
    """Point mutmut's ``only_mutate`` and targeted tests at what this shard runs."""

    path = root / "pyproject.toml"
    text = path.read_text(encoding="utf-8")
    if "only_mutate" in text:
        raise SystemExit("pyproject.toml already sets only_mutate")
    if MUTMUT_MARKER not in text:
        raise SystemExit("pyproject.toml is missing the mutmut coverage marker")
    block = "only_mutate = [\n" + "".join(f'  "{item}",\n' for item in files) + "]\n"
    new_text = text.replace(MUTMUT_MARKER, MUTMUT_MARKER + block, 1)
    if shard and shard in SHARD_TEST_SELECTION and TEST_SELECTION_MARKER in new_text:
        selection = SHARD_TEST_SELECTION[shard]
        formatted = (
            "pytest_add_cli_args_test_selection = [\n"
            + "".join(f'  "{item}",\n' for item in selection)
            + "]\n"
        )
        new_text = new_text.replace(TEST_SELECTION_MARKER, formatted, 1)
    path.write_text(new_text, encoding="utf-8")


def publish_count(count: int) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        return
    with open(output, "a", encoding="utf-8") as handle:
        handle.write(f"count={count}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shard", required=True, choices=[name for name, _prefix in SHARDS])
    parser.add_argument("--event", default=os.environ.get("MUTATION_EVENT", "pull_request"))
    parser.add_argument("--base", default=os.environ.get("MUTATION_BASE", ""))
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    root = args.root.resolve()
    if args.event == "pull_request":
        if not args.base:
            raise SystemExit("a pull request needs MUTATION_BASE or --base")
        changed = changed_files(args.base)
        functions = exception_functions_in_diff(
            _git_diff(args.base, "policies/mutation-exceptions.json")
        )
        files = select(root, args.shard, changed, functions)
    else:
        files = select(root, args.shard, None)
    (root / "mutation-scope.txt").write_text("".join(f"{path}\n" for path in files), encoding="utf-8")
    if files:
        restrict_mutmut(root, files, args.shard)
    publish_count(len(files))
    print(json.dumps({"shard": args.shard, "event": args.event, "count": len(files), "files": files}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
