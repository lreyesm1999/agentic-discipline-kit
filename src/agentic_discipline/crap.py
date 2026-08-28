from __future__ import annotations


def crap_score(complexity: float, coverage_percent: float) -> float:
    """Calculate Change Risk Anti-Patterns (CRAP) score."""
    coverage = max(0.0, min(1.0, coverage_percent / 100.0))
    return complexity**2 * (1 - coverage) ** 3 + complexity
