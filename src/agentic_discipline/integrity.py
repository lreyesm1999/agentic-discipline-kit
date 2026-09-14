from __future__ import annotations

import re
from dataclasses import dataclass

PATTERNS: dict[str, str] = {
    "test_skip": r"\b(test|describe)\.skip\b|\bxit\b|\bxdescribe\b|pytest\.skip|@Disabled",
    "coverage_ignore": r"pragma:\s*no cover|istanbul ignore",
    "mutation_disable": r"stryker\s+disable|mutation.*exclude",
    "lint_disable": r"eslint-disable",
    "type_ignore": r"type:\s*ignore|@ts-ignore",
    "broad_swallow": r"except\s+Exception\s*:\s*(pass|\.\.\.)|catch\s*\([^)]*\)\s*\{\s*\}",
    "gate_noop": (
        r"[\"']command[\"']\s*:\s*(?:[\"']\s*(true|echo|exit\s+0)|"
        r"\[\s*[\"']\s*(true|echo))"
    ),
}

GATE_CONFIGURATION_FILES = {"pyproject.toml", "pytest.ini", "tox.ini", ".coveragerc"}
GATE_CONFIGURATION_PREFIXES = (".github/workflows/", ".agentic/")
GENERATED_EVIDENCE_PREFIXES = ("docs/v2/evidence/",)

GATE_PATTERNS: dict[str, str] = {
    "threshold_change": r"(coverage|mutation|threshold|fail-under).{0,40}\d+",
    "workflow_disable": r"\bif\s*:\s*(false|\$\{\{\s*false\s*\}\})|continue-on-error\s*:\s*true",
}

DELETION_PATTERNS: dict[str, str] = {
    "assertion_removed": r"\bassert\b|expect\s*\(|Assert\.",
    "test_removed": r"\bdef\s+test_|\b(test|it)\s*\(",
    "gate_removed": r"\b(run|command|threshold|coverage|mutation|security|protected)\b",
}


@dataclass(frozen=True)
class IntegrityFinding:
    file: str | None
    pattern: str
    line: str


def is_gate_configuration(path: str | None) -> bool:
    return bool(
        path and (path in GATE_CONFIGURATION_FILES or path.startswith(GATE_CONFIGURATION_PREFIXES))
    )


def is_generated_evidence(path: str | None) -> bool:
    return bool(path and path.startswith(GENERATED_EVIDENCE_PREFIXES))


def is_test_file(path: str | None) -> bool:
    return bool(path and (path.startswith("tests/") or "/tests/" in path))


def audit_diff(diff_text: str) -> list[IntegrityFinding]:
    findings: list[IntegrityFinding] = []
    current_file: str | None = None
    updated_test_assertions: set[str] = set()

    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
        elif (
            line.startswith("+")
            and not line.startswith("+++")
            and is_test_file(current_file)
            and re.search(DELETION_PATTERNS["assertion_removed"], line[1:])
        ):
            if current_file is not None:
                updated_test_assertions.add(current_file)

    current_file = None

    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
            continue
        if line.startswith("+") and not line.startswith("+++"):
            added = line[1:]
            for name, pattern in PATTERNS.items():
                if re.search(pattern, added, re.IGNORECASE):
                    findings.append(IntegrityFinding(current_file, name, added[:500]))
            if is_gate_configuration(current_file):
                for name, pattern in GATE_PATTERNS.items():
                    if re.search(pattern, added, re.IGNORECASE):
                        findings.append(IntegrityFinding(current_file, name, added[:500]))
        elif line.startswith("-") and not line.startswith("---"):
            removed = line[1:]
            if is_generated_evidence(current_file):
                continue
            if is_test_file(current_file):
                deletion_patterns = {
                    name: pattern
                    for name, pattern in DELETION_PATTERNS.items()
                    if name in {"assertion_removed", "test_removed"}
                }
            elif is_gate_configuration(current_file):
                deletion_patterns = {"gate_removed": DELETION_PATTERNS["gate_removed"]}
            else:
                deletion_patterns = {}
            for name, pattern in deletion_patterns.items():
                if name == "assertion_removed" and current_file in updated_test_assertions:
                    continue
                if re.search(pattern, removed, re.IGNORECASE):
                    findings.append(IntegrityFinding(current_file, name, removed[:500]))

    return findings
