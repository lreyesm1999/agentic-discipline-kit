#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

REQUIRED = [
    "README.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
    "SUPPORT.md",
    "GOVERNANCE.md",
    "CHANGELOG.md",
    "AGENTS.md",
    "MASTER_PROMPT.md",
    "scripts/bootstrap_project.py",
    "scripts/coverage_gate.py",
    "GITHUB_SETUP.md",
    "pyproject.toml",
    ".github/pull_request_template.md",
    ".github/dependabot.yml",
    ".github/CODEOWNERS",
    ".github/workflows/ci.yml",
    ".github/workflows/security.yml",
    "schemas/agentic-config.schema.json",
    "config/self-quality.json",
    "specs/PROD-001.md",
    "acceptance/production-hardening.feature",
]


def main() -> int:
    missing = [item for item in REQUIRED if not Path(item).exists()]
    skills = list(Path("skills").glob("*/SKILL.md"))
    versions = {
        "VERSION": Path("VERSION").read_text(encoding="utf-8").strip(),
        "package": __import__("agentic_discipline").__version__,
    }
    workflow = Path(".github/workflows/agentic-integrity.yml").read_text(encoding="utf-8")
    manifest = json.loads(Path("MANIFEST.json").read_text(encoding="utf-8"))
    manifest_errors: list[str] = []
    for entry in manifest.get("files", []):
        path = Path(entry["path"])
        if not path.is_file():
            manifest_errors.append(f"missing:{path.as_posix()}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            manifest_errors.append(f"hash:{path.as_posix()}")
    checks = {
        "version_consistent": len(set(versions.values())) == 1,
        "protected_workflow": "agentic-discipline protected" in workflow,
        "manifest_integrity": not manifest_errors,
    }
    result = {
        "missing_required_files": missing,
        "skills": len(skills),
        "versions": versions,
        "checks": checks,
        "manifest_errors": manifest_errors,
        "status": (
            "PASS" if not missing and len(skills) == 20 and all(checks.values()) else "FAIL"
        ),
    }
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
