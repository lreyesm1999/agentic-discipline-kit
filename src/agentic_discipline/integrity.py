from __future__ import annotations

import re
from collections.abc import Callable
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

GATE_CONFIGURATION_FILES = {
    "pyproject.toml",
    "pytest.ini",
    "tox.ini",
    ".coveragerc",
}
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


# A removed test is only evidence of weakened verification while the code it exercised
# still exists. When the same change deletes that code, the test cannot run any more
# and is retired with it; the audit still lists it so a reviewer sees what went.
DEFINITION = r"^\s*(?:export\s+)?(?:async\s+)?(?:def|class|function)\s+([A-Za-z_]\w*)"
CALL = r"([A-Za-z_]\w*)\s*\("


@dataclass(frozen=True)
class IntegrityAudit:
    findings: list[IntegrityFinding]
    retired: list[IntegrityFinding]


@dataclass
class _Removal:
    line: str
    run: int


def _file_changes(diff_text: str) -> list[tuple[str | None, str]]:
    """Pair each line with the file it belongs to; a deleted file keeps its old path."""

    paired: list[tuple[str | None, str]] = []
    current_file: str | None = None
    previous = ""
    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
        elif line == "+++ /dev/null" and previous.startswith("--- a/"):
            current_file = previous[6:]
        paired.append((current_file, line))
        previous = line
    return paired


def audit_diff(diff_text: str) -> list[IntegrityFinding]:
    """Audit a diff without looking at the repository, so no test counts as retired."""

    return audit_changes(diff_text, still_defined=lambda name: True).findings


def audit_changes(diff_text: str, still_defined: Callable[[str], bool]) -> IntegrityAudit:
    findings: list[IntegrityFinding] = []
    changes = _file_changes(diff_text)
    updated_test_assertions: set[str] = set()
    added_definitions: set[str] = set()
    removed_definitions: set[str] = set()

    for current_file, line in changes:
        if line.startswith("+") and not line.startswith("+++"):
            definition = re.match(DEFINITION, line[1:])
            if definition:
                added_definitions.add(definition.group(1))
            if is_test_file(current_file) and re.search(
                DELETION_PATTERNS["assertion_removed"], line[1:]
            ):
                if current_file is not None:
                    updated_test_assertions.add(current_file)
        elif line.startswith("-") and not line.startswith("---"):
            definition = re.match(DEFINITION, line[1:])
            if definition and not is_test_file(current_file):
                removed_definitions.add(definition.group(1))

    gone: dict[str, bool] = {}

    def retires(removed: str) -> bool:
        for name in re.findall(CALL, removed):
            if name not in removed_definitions or name in added_definitions:
                continue
            if name not in gone:
                gone[name] = not still_defined(name)
            if gone[name]:
                return True
        return False

    candidates: list[tuple[IntegrityFinding, _Removal]] = []
    test_removals: list[_Removal] = []
    run = 0

    for current_file, line in changes:
        if line.startswith("+++"):
            run += 1
            continue
        if line.startswith("+"):
            run += 1
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
                removal = _Removal(removed, run)
                test_removals.append(removal)
            elif is_gate_configuration(current_file):
                deletion_patterns = {"gate_removed": DELETION_PATTERNS["gate_removed"]}
                removal = _Removal(removed, run)
            else:
                continue
            for name, pattern in deletion_patterns.items():
                if name == "assertion_removed" and current_file in updated_test_assertions:
                    continue
                if re.search(pattern, removed, re.IGNORECASE):
                    finding = IntegrityFinding(current_file, name, removed[:500])
                    findings.append(finding)
                    candidates.append((finding, removal))
        else:
            run += 1

    retired: list[IntegrityFinding] = []
    for finding, removal in candidates:
        if finding.pattern == "assertion_removed":
            is_retired = retires(removal.line)
        else:
            is_retired = finding.pattern == "test_removed" and _test_is_retired(
                removal, test_removals, retires
            )
        if is_retired:
            retired.append(finding)
    retired_ids = {id(finding) for finding in retired}
    return IntegrityAudit(
        findings=[finding for finding in findings if id(finding) not in retired_ids],
        retired=retired,
    )


def _test_is_retired(
    start: _Removal, test_removals: list[_Removal], retires: Callable[[str], bool]
) -> bool:
    """A removed test is retired when every assertion it lost calls deleted code."""

    index = next(i for i, removal in enumerate(test_removals) if removal is start)
    body = [start]
    for removal in test_removals[index + 1 :]:
        if removal.run != start.run:
            break
        if re.search(DELETION_PATTERNS["test_removed"], removal.line, re.IGNORECASE):
            break
        body.append(removal)
    assertions = [
        removal.line
        for removal in body
        if re.search(DELETION_PATTERNS["assertion_removed"], removal.line, re.IGNORECASE)
    ]
    return bool(assertions) and all(retires(line) for line in assertions)
