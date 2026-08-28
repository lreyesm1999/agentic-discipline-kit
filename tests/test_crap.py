from agentic_discipline.crap import crap_score


def test_crap_score_is_complexity_at_full_coverage() -> None:
    assert crap_score(8, 100) == 8


def test_crap_score_penalizes_low_coverage() -> None:
    assert crap_score(10, 0) == 110


def test_crap_score_clamps_coverage() -> None:
    assert crap_score(4, 150) == 4
