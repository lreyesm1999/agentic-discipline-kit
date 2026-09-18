"""The discovery scan report, file by file and area by area.

``discovery.scan`` is the static inventory an agent reads before trusting any
knowledge about a repository. Existing tests never compared its report, so a file
could land in the wrong area, lose its symbols, leak an unredacted excerpt, or be
counted as inspected when it was not. The repository below has one file of every
kind the scan distinguishes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agentic_discipline.bootstrap import find_contract_root
from agentic_discipline.common import run_git
from agentic_discipline.control.contracts import ControlError, digest, redact
from agentic_discipline.control.discovery import fingerprint, scan
from agentic_discipline.profiles import detect_projects, load_profiles

MEANING = "bounded static inspection, not verified runtime understanding"
AREAS = ("source", "tests", "docs", "ci", "config", "persistence", "agent_instructions")
APP = (
    b"import os\n"
    b"from pathlib import Path\n"
    b"from .helpers import tool\n"
    b"\n"
    b"class Service:\n"
    b"    def run(self):\n"
    b"        return os.sep\n"
    b"\n"
    b"async def fetch():\n"
    b"    return Path('.')\n"
)
APP_SYMBOLS = [
    {"name": "os", "line": 1, "type": "Import", "level": 0},
    {"name": "pathlib", "line": 2, "type": "Import", "level": 0},
    {"name": "helpers", "line": 3, "type": "Import", "level": 1},
    {"name": "Service", "line": 5, "type": "ClassDef"},
    {"name": "Service.run", "line": 6, "type": "FunctionDef"},
    {"name": "fetch", "line": 9, "type": "AsyncFunctionDef"},
]
# Every inspected Python file carries its symbols; everything else carries none.
SYMBOLS = {
    "app.py": APP_SYMBOLS,
    "tests/test_app.py": [{"name": "test_ok", "line": 1, "type": "FunctionDef"}],
}

# path -> (bytes, area, reason)
FILES: dict[str, tuple[bytes, str, str]] = {
    "AGENTS.md": (b"# Agents\n", "agent_instructions", ""),
    "skills/review/SKILL.md": (b"# Review\n", "agent_instructions", ""),
    ".github/workflows/ci.yml": (b"name: ci\n", "ci", ""),
    "tests/test_app.py": (b"def test_ok():\n    assert True\n", "tests", ""),
    "README.md": (b"Deploy with password=hunter2 today\n", "docs", ""),
    "notes/big.txt": (b"x" * 300, "docs", "size limit"),
    "db/migration_001.sql": (b"CREATE TABLE t (id int);\n", "persistence", ""),
    "pyproject.toml": (b"[project]\nname = 'demo'\n", "config", ""),
    "app.py": (APP, "source", ""),
    "broken.py": (b"def broken(:\n", "source", "invalid Python syntax"),
    "blob.dat": (b"a\x00b", "source", "binary"),
    "latin.dat": (b"\xff\xfe", "source", "binary"),
}


def _write(root: Path, files: dict[str, bytes]) -> None:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _write(root, {name: content for name, (content, _, _) in FILES.items()})
    (root / ".env").write_text("API_KEY=never-scanned\n")
    run_git(["init"], cwd=root)
    run_git(["config", "user.name", "Scan Test"], cwd=root)
    run_git(["config", "user.email", "scan@example.invalid"], cwd=root)
    run_git(["add", "."], cwd=root)
    run_git(["commit", "-m", "baseline"], cwd=root)
    return root


def test_scan_reports_every_file_area_and_reason(repository: Path) -> None:
    (repository / "untracked.txt").write_bytes(b"pending\n")  # makes the tree dirty
    report = scan(repository, max_bytes=200)
    snapshots = fingerprint(repository)

    assert list(report) == ["root", "commit", "dirty", "fingerprint", "files", "coverage", "stacks"]
    assert report["root"] == str(repository)
    assert report["commit"] == run_git(["rev-parse", "HEAD"], cwd=repository).strip()
    assert report["dirty"] is True
    assert report["fingerprint"] == digest(snapshots)
    assert ".env" not in snapshots

    expected_files = {**FILES, "untracked.txt": (b"pending\n", "docs", "")}
    observations = {item["path"]: item for item in report["files"]}
    assert [item["path"] for item in report["files"]] == list(snapshots)
    assert set(observations) == set(expected_files)
    for name, (content, area, reason) in expected_files.items():
        text = "" if reason else content.decode("utf-8")
        assert observations[name] == {
            "path": name,
            "content_hash": snapshots[name],
            "area": area,
            "inspected": not reason,
            "reason": reason,
            "excerpt": redact(text[:4000]),
            "symbols": SYMBOLS.get(name, []),
        }, name
    assert "hunter2" not in observations["README.md"]["excerpt"]

    counts = {area: {"total": 0, "inspected": 0, "unknown": 0} for area in AREAS}
    for _, area, reason in expected_files.values():
        counts[area]["total"] += 1
        counts[area]["unknown" if reason else "inspected"] += 1
    assert report["coverage"] == {
        **{
            area: {
                **data,
                "status": "EXHAUSTIVE" if data["inspected"] == data["total"] else "PARTIAL",
                "meaning": MEANING,
            }
            for area, data in counts.items()
        },
        "runtime": {"status": "NOT_STARTED", "total": None, "inspected": 0, "unknown": None},
    }
    assert report["coverage"]["source"]["status"] == "PARTIAL"
    assert report["coverage"]["tests"]["status"] == "EXHAUSTIVE"

    detections = detect_projects(repository, load_profiles(find_contract_root()))
    assert detections
    assert report["stacks"] == [
        {
            "profile": d.profile,
            "root": str(d.root.relative_to(repository)),
            "evidence": list(d.evidence),
        }
        for d in detections
    ]


def test_scan_of_a_clean_single_file_repository(tmp_path: Path) -> None:
    root = tmp_path / "tiny"
    root.mkdir()
    _write(root, {"app.py": b"value = 1\n"})
    report = scan(root)

    assert report["commit"] == ""
    assert report["dirty"] is False
    assert report["stacks"] == []
    assert report["coverage"]["source"] == {
        "total": 1,
        "inspected": 1,
        "unknown": 0,
        "status": "EXHAUSTIVE",
        "meaning": MEANING,
    }
    for area in AREAS[1:]:
        assert report["coverage"][area] == {
            "total": 0,
            "inspected": 0,
            "unknown": 0,
            "status": "NOT_APPLICABLE",
            "meaning": MEANING,
        }


def test_default_limits_on_a_clean_committed_repository(tmp_path: Path) -> None:
    root = tmp_path / "limits"
    root.mkdir()
    long_text = "".join(f"line {index:05d}\n" for index in range(400))  # 4,400 characters
    _write(
        root,
        {
            "at_limit.txt": b"a" * 262144,
            "over_limit.txt": b"b" * 262145,
            "long.md": long_text.encode("utf-8"),
        },
    )
    run_git(["init"], cwd=root)
    run_git(["config", "user.name", "Scan Test"], cwd=root)
    run_git(["config", "user.email", "scan@example.invalid"], cwd=root)
    run_git(["add", "."], cwd=root)
    run_git(["commit", "-m", "baseline"], cwd=root)

    report = scan(root)
    files = {item["path"]: item for item in report["files"]}
    assert report["dirty"] is False
    assert report["commit"] == run_git(["rev-parse", "HEAD"], cwd=root).strip()
    assert (files["at_limit.txt"]["inspected"], files["at_limit.txt"]["reason"]) == (True, "")
    assert (files["over_limit.txt"]["inspected"], files["over_limit.txt"]["reason"]) == (
        False,
        "size limit",
    )
    assert files["long.md"]["excerpt"] == long_text[:4000]


def test_scan_requires_a_repository_directory(tmp_path: Path) -> None:
    file = tmp_path / "file.txt"
    file.write_text("x")
    for root in (file, Path(tmp_path.anchor)):
        with pytest.raises(ControlError) as caught:
            scan(root)
        assert (caught.value.code, str(caught.value)) == (
            "INVALID_ROOT",
            "Choose a repository directory",
        )
