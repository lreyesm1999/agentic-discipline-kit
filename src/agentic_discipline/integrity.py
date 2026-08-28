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
    "threshold_change": r"(coverage|mutation|threshold|fail-under).{0,40}\d+",
    "workflow_disable": r"\bif\s*:\s*(false|\$\{\{\s*false\s*\}\})|continue-on-error\s*:\s*true",
    "gate_noop": (
        r"[\"']command[\"']\s*:\s*(?:[\"']\s*(true|echo|exit\s+0)|"
        r"\[\s*[\"']\s*(true|echo))"
    ),
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


def audit_diff(diff_text: str) -> list[IntegrityFinding]:
    findings: list[IntegrityFinding] = []
    current_file: str | None = None

    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
            continue
        if line.startswith("+") and not line.startswith("+++"):
            added = line[1:]
            for name, pattern in PATTERNS.items():
                if re.search(pattern, added, re.IGNORECASE):
                    findings.append(IntegrityFinding(current_file, name, added[:500]))
        elif line.startswith("-") and not line.startswith("---"):
            removed = line[1:]
            for name, pattern in DELETION_PATTERNS.items():
                if re.search(pattern, removed, re.IGNORECASE):
                    findings.append(IntegrityFinding(current_file, name, removed[:500]))

    return findings
