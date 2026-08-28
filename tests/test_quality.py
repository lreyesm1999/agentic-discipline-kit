from agentic_discipline.quality import evaluate_thresholds, extract_metrics


def test_regex_metric_parser() -> None:
    metrics = extract_metrics(
        "Lines : 94.7%\nBranches : 90.1%",
        {
            "type": "regex",
            "metrics": {
                "lines": r"Lines\s*:\s*([0-9.]+)%",
                "branches": r"Branches\s*:\s*([0-9.]+)%",
            },
        },
    )
    assert metrics == {"lines": 94.7, "branches": 90.1}


def test_unknown_metric_fails_threshold() -> None:
    failures = evaluate_thresholds({}, {"coverage": {"min": 90}})
    assert failures == ["coverage=UNKNOWN"]


def test_threshold_failure_is_explicit() -> None:
    failures = evaluate_thresholds({"coverage": 80.0}, {"coverage": {"min": 90}})
    assert failures == ["coverage 80.0 < 90"]
