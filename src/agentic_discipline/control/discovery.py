"""Read-only, bounded repository observation; never execute discovered instructions."""

from __future__ import annotations

import ast
import hashlib
import os
import subprocess
from pathlib import Path
from typing import Any

from ..bootstrap import find_contract_root
from ..profiles import detect_projects, load_profiles
from .contracts import digest, redact, require

EXCLUDED = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".hypothesis",
    "artifacts",
    ".agent-memory",
}
SECRET_NAMES = {
    "credentials",
    "credentials.json",
    "secrets.json",
    "secrets.yaml",
    ".npmrc",
    ".pypirc",
    "id_rsa",
    "id_ed25519",
}


def allowed(path: Path) -> bool:
    return not (
        set(path.parts) & EXCLUDED
        or (
            ".agentic" in path.parts
            and any(p == "control" or p.startswith("adopt-") for p in path.parts)
        )
        or path.name.startswith(".env")
        or path.name.lower() in SECRET_NAMES
        or path.suffix in {".pem", ".key", ".p12", ".pyc"}
        or any(p.endswith(".egg-info") for p in path.parts)
    )


def git(root: Path, args: list[str]) -> str:
    # Git writes UTF-8, and `ls-files -z` leaves non-ASCII paths unquoted; the locale
    # default on Windows is a legacy code page that would misread them.
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=30,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def files(root: Path, include_ignored: bool = False, scope: list[str] | None = None) -> list[Path]:
    result: list[Path] = []
    # Git honours nested ignore rules, while the fallback permits non-Git adoption.
    if not include_ignored and git(root, ["rev-parse", "--is-inside-work-tree"]) == "true":
        output = git(root, ["ls-files", "--cached", "--others", "--exclude-standard", "-z"])
        candidates = [Path(p) for p in output.split("\x00") if p]
    else:
        candidates = []
        for folder, dirs, names in os.walk(root, followlinks=False):
            dirs[:] = [
                d
                for d in dirs
                if allowed(Path(folder).relative_to(root) / d)
                and not (Path(folder) / d).is_symlink()
            ]
            candidates.extend(Path(folder).relative_to(root) / n for n in names)
    for relative in sorted(set(candidates)):
        if scope is not None and not any(
            s == "."
            or relative.as_posix() == s
            or relative.as_posix().startswith(s.rstrip("/") + "/")
            for s in scope
        ):
            continue
        path = root / relative
        if (
            allowed(relative)
            and path.is_file()
            and not any(
                (root / Path(*relative.parts[:i])).is_symlink()
                for i in range(1, len(relative.parts) + 1)
            )
        ):
            result.append(relative)
    return result


def fingerprint(root: Path, scope: list[str] | None = None) -> dict[str, str]:
    result = {}
    for relative in files(root, include_ignored=True, scope=scope):
        name = relative.as_posix()
        path = root / relative
        with path.open("rb") as source:
            result[name] = hashlib.file_digest(source, "sha256").hexdigest()
    return result


def line_counts(root: Path, names: list[str]) -> dict[str, int]:
    """Retain deletion cost as well as the size of newly written files."""
    result = {}
    for name in names:
        with (root / name).open("rb") as source:
            result[name] = sum(1 for _ in source)
    return result


def link_fingerprint(root: Path) -> dict[str, str]:
    """Measure link identity for scope accounting without following its target."""
    result = {}
    for folder, dirs, names in os.walk(root, followlinks=False):
        for name in dirs + names:
            path = Path(folder) / name
            relative = path.relative_to(root)
            if allowed(relative) and path.is_symlink():
                result[relative.as_posix()] = digest({"link": os.readlink(path)})
        dirs[:] = [
            d
            for d in dirs
            if allowed(Path(folder).relative_to(root) / d) and not (Path(folder) / d).is_symlink()
        ]
    return result


def validate_inputs(root: Path, scope: list[str]) -> None:
    """A verifier cannot claim freshness for data outside the measured workspace."""
    for value in scope:
        relative = Path(value)
        require(
            value == "." or allowed(relative),
            "UNTRACKED_INPUT",
            "Verifier input is excluded from measurement",
        )
        require(
            not any(
                (root / Path(*relative.parts[:i])).is_symlink()
                for i in range(1, len(relative.parts) + 1)
            ),
            "UNTRACKED_INPUT",
            "Verifier inputs cannot follow symlinks",
        )
    for folder, dirs, names in os.walk(root, followlinks=False):
        for name in dirs + names:
            relative = (Path(folder) / name).relative_to(root)
            if allowed(relative) and any(
                s == "."
                or relative.as_posix() == s
                or relative.as_posix().startswith(s.rstrip("/") + "/")
                for s in scope
            ):
                require(
                    not (root / relative).is_symlink(),
                    "UNTRACKED_INPUT",
                    "Symlink in verifier inputs; use contained, measured files",
                )
        dirs[:] = [
            d
            for d in dirs
            if allowed(Path(folder).relative_to(root) / d) and not (Path(folder) / d).is_symlink()
        ]


def area(path: Path) -> str:
    if path.name in {"AGENTS.md", "CLAUDE.md", "GEMINI.md"} or "skills" in path.parts:
        return "agent_instructions"
    if ".github" in path.parts:
        return "ci"
    if "test" in path.as_posix().lower():
        return "tests"
    if path.suffix in {".md", ".rst", ".txt"}:
        return "docs"
    if "migration" in path.as_posix() or path.suffix == ".sql":
        return "persistence"
    if path.suffix in {".json", ".toml", ".yaml", ".yml", ".ini"}:
        return "config"
    return "source"


def python_symbols(tree: ast.AST, prefix: str = "") -> list[dict[str, Any]]:
    result = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = prefix + node.name
            result.append({"name": name, "line": node.lineno, "type": type(node).__name__})
            result.extend(python_symbols(node, name + "."))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names = (
                [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else [a.name for a in node.names]
            )
            result.extend(
                {
                    "name": name,
                    "line": node.lineno,
                    "type": "Import",
                    "level": getattr(node, "level", 0),
                }
                for name in names
            )
        else:
            result.extend(python_symbols(node, prefix))
    return result


def scan(root: Path, *, max_bytes: int = 262144) -> dict[str, Any]:
    require(
        root.is_dir() and root != Path(root.anchor), "INVALID_ROOT", "Choose a repository directory"
    )
    snapshots = fingerprint(root)
    observations = []
    coverage: dict[str, dict[str, Any]] = {
        a: {"total": 0, "inspected": 0, "unknown": 0}
        for a in ("source", "tests", "docs", "ci", "config", "persistence", "agent_instructions")
    }
    for name, content_hash in snapshots.items():
        path = root / name
        category = area(Path(name))
        coverage[category]["total"] += 1
        text = ""
        reason = ""
        if path.stat().st_size > max_bytes:
            reason = "size limit"
        else:
            try:
                text = path.read_text(encoding="utf-8")
                if "\x00" in text:
                    reason = "binary"
            except UnicodeError:
                reason = "binary"
        symbols: list[dict[str, Any]] = []
        if not reason and path.suffix == ".py":
            try:
                tree = ast.parse(text)
                symbols = python_symbols(tree)
            except SyntaxError:
                reason = "invalid Python syntax"
        coverage[category]["unknown" if reason else "inspected"] += 1
        observations.append(
            {
                "path": name,
                "content_hash": content_hash,
                "area": category,
                "inspected": not bool(reason),
                "reason": reason,
                "excerpt": redact(text[:4000]) if not reason else "",
                "symbols": symbols,
            }
        )
    for data in coverage.values():
        data["status"] = (
            "NOT_APPLICABLE"
            if not data["total"]
            else "EXHAUSTIVE"
            if data["inspected"] == data["total"]
            else "PARTIAL"
        )
        data["meaning"] = "bounded static inspection, not verified runtime understanding"
    coverage["runtime"] = {"status": "NOT_STARTED", "total": None, "inspected": 0, "unknown": None}
    detections = detect_projects(root, load_profiles(find_contract_root()))
    return {
        "root": str(root),
        "commit": git(root, ["rev-parse", "HEAD"]),
        "dirty": bool(git(root, ["status", "--porcelain"])),
        "fingerprint": digest(snapshots),
        "files": observations,
        "coverage": coverage,
        "stacks": [
            {
                "profile": d.profile,
                "root": str(d.root.relative_to(root)),
                "evidence": list(d.evidence),
            }
            for d in detections
        ],
    }
