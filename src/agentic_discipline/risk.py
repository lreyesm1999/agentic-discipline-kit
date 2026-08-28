from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .validation import load_json

WEIGHTS: dict[str, int] = {
    "auth": 25,
    "money": 30,
    "migration": 22,
    "public_api": 18,
    "concurrency": 18,
    "security": 22,
    "architecture": 14,
    "infra": 12,
    "destructive": 25,
    "crypto": 25,
}

PATTERNS: dict[str, str] = {
    "auth": r"(auth|permission|role|policy|jwt|oauth|session)",
    "money": r"(payment|billing|invoice|balance|ledger|pnl|price|money|wallet)",
    "migration": r"(migration|schema|prisma|alembic|ef migrations|ddl)",
    "public_api": r"(api/|controller|route|endpoint|openapi|graphql)",
    "concurrency": r"(lock|mutex|semaphore|transaction|concurr|race|async)",
    "security": r"(security|secret|token|password|sanitize|encrypt|decrypt)",
    "architecture": r"(domain/|core/|infrastructure/|architecture)",
    "infra": r"(docker|kubernetes|terraform|deploy|ci/|github/workflows)",
    "destructive": r"(delete|drop|truncate|purge|destroy)",
    "crypto": r"(crypto|cipher|hash|signature|rsa|aes)",
}


@dataclass(frozen=True)
class RiskAssessment:
    score: int
    level: str
    files_changed: int
    factors: dict[str, bool]


def assess_risk(diff_text: str, files: Iterable[str]) -> RiskAssessment:
    return assess_risk_with_weights(diff_text, files, WEIGHTS)


def load_risk_weights(path: Path) -> dict[str, int]:
    raw = load_json(path, "risk weights")
    weights: dict[str, int] = {}
    for name in PATTERNS:
        value = raw.get(name)
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"risk weight {name!r} must be a non-negative integer")
        weights[name] = value
    return weights


def assess_risk_with_weights(
    diff_text: str, files: Iterable[str], weights: dict[str, int]
) -> RiskAssessment:
    file_list = list(files)
    added_lines = [
        line[1:]
        for line in diff_text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    normalized = "\n".join([*file_list, *added_lines]).lower()
    score = min(len(file_list) * 2, 20)
    factors: dict[str, bool] = {}

    for name, pattern in PATTERNS.items():
        hit = bool(re.search(pattern, normalized, re.IGNORECASE))
        factors[name] = hit
        if hit:
            score += weights[name]

    score = min(score, 100)
    if score < 15:
        level = "LOW"
    elif score < 40:
        level = "STANDARD"
    elif score < 75:
        level = "HIGH"
    else:
        level = "CRITICAL"

    return RiskAssessment(score, level, len(file_list), factors)


def level_at_least(level: str, threshold: str) -> bool:
    order = {"LOW": 0, "STANDARD": 1, "HIGH": 2, "CRITICAL": 3}
    return order[level] >= order[threshold]
