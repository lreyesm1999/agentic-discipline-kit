"""Invariants of the assurance engine, stated as properties over generated inputs.

These say what must hold for every combination, not for the handful a scenario happens
to exercise: adding a failure cannot produce VERIFIED, staling the only proof cannot
leave VERIFIED, more impact cannot ask for less, and completion implies no proof debt.
"""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from agentic_discipline.control.assurance import model, resolver
from agentic_discipline.control.assurance.registry import Registry

RESULTS = st.sampled_from(["PASS", "FAIL", "BLOCKED", "UNKNOWN"])
CLASSES = st.sampled_from(["DETERMINISTIC", "MEASURED", "AGENT_JUDGMENT", "HUMAN"])
CRITICALITIES = st.sampled_from(model.CRITICALITY)
CAPABILITIES = st.sampled_from(sorted(model.CAPABILITIES))


def _obligation(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "PO-1",
        "task_id": "TASK-1",
        "claim": "The value is one",
        "origin": {
            "requirement_ids": [],
            "acceptance_ids": [0],
            "policy_ids": [],
            "architecture_ids": [],
            "generated_reason": "acceptance criterion",
        },
        "derivation": "CONTRACT",
        "criticality": "STANDARD",
        "mandatory": True,
        "status": "UNRESOLVED",
        "phase": "RECONCILED",
        "enforced": True,
        "acceptable_proof_capabilities": ["unit"],
        "required_verifiers": ["V1"],
        "affected_paths": ["src"],
        "affected_symbols": [],
        "dependencies": [],
        "plan": {"deterministic_available": [], "human_required": False, "route": "unit"},
    }
    base.update(overrides)
    return base


def _evidence(identifier: str, verifier: str, result: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": identifier,
        "verifier": verifier,
        "result": result,
        "acceptance": [0],
        "obligation_ids": ["PO-1"],
        "obligation_bindings": {"PO-1": {"files": {"src/a.py": "hash"}}},
        "binding": {"files": {"src/a.py": "hash"}},
        "run_consistent": True,
        "evidence_class": "DETERMINISTIC",
        **extra,
    }


def _resolve(
    monkeypatch: Any, obligation: dict[str, Any], records: list[dict[str, Any]]
) -> dict[str, Any]:
    monkeypatch.setattr(resolver, "artifact_intact", lambda plane, evidence: True)
    monkeypatch.setattr(resolver, "outcome_matches", lambda plane, evidence: True)
    monkeypatch.setattr(
        resolver, "obligation_binding", lambda plane, task, o: {"files": {"src/a.py": "hash"}}
    )
    return resolver.resolve(
        object(),
        {"id": "TASK-1", "acceptance": ["The value is one"], "scope": ["src"]},
        obligation,
        evidence=records,
        task_binding={"files": {"src/a.py": "hash"}},
    )


# --- resolution invariants ------------------------------------------------------------


@settings(max_examples=120, deadline=None)
@given(
    passes=st.integers(min_value=0, max_value=3),
    failures=st.integers(min_value=1, max_value=3),
)
def test_a_current_failure_never_leaves_an_obligation_verified(passes: int, failures: int) -> None:
    with pytest.MonkeyPatch.context() as monkeypatch:
        records = [_evidence(f"P{i}", "V1", "PASS") for i in range(passes)]
        records += [_evidence(f"F{i}", "V1", "FAIL") for i in range(failures)]

        status = _resolve(monkeypatch, _obligation(), records)["status"]

        assert status != "VERIFIED"
        assert status == ("CONFLICTED" if passes else "FAILED")


@settings(max_examples=120, deadline=None)
@given(results=st.lists(RESULTS, min_size=1, max_size=4))
def test_verified_happens_only_when_every_required_verifier_currently_passes(
    results: list[str],
) -> None:
    with pytest.MonkeyPatch.context() as monkeypatch:
        verifiers = [f"V{i}" for i in range(len(results))]
        records = [
            _evidence(f"E{i}", verifier, result)
            for i, (verifier, result) in enumerate(zip(verifiers, results, strict=True))
        ]

        resolution = _resolve(monkeypatch, _obligation(required_verifiers=verifiers), records)

        assert (resolution["status"] == "VERIFIED") == all(r == "PASS" for r in results)


@settings(max_examples=100, deadline=None)
@given(stale=st.booleans(), inconsistent=st.booleans())
def test_staling_the_only_proof_cannot_leave_an_obligation_verified(
    stale: bool, inconsistent: bool
) -> None:
    with pytest.MonkeyPatch.context() as monkeypatch:
        record = _evidence("E1", "V1", "PASS")
        if stale:
            record["obligation_bindings"] = {"PO-1": {"files": {"src/a.py": "moved"}}}
        if inconsistent:
            record["run_consistent"] = False

        resolution = _resolve(monkeypatch, _obligation(), [record])

        assert (resolution["status"] == "VERIFIED") == (not stale and not inconsistent)
        if stale or inconsistent:
            assert resolution["status"] == "STALE"


@settings(max_examples=100, deadline=None)
@given(evidence_class=CLASSES, dominated=st.booleans())
def test_judgment_never_closes_a_claim_a_deterministic_verifier_could_reach(
    evidence_class: str, dominated: bool
) -> None:
    with pytest.MonkeyPatch.context() as monkeypatch:
        obligation = _obligation(
            plan={
                "deterministic_available": ["unit"] if dominated else [],
                "human_required": False,
                "route": "unit",
            }
        )
        record = _evidence("E1", "V1", "PASS", evidence_class=evidence_class)

        status = _resolve(monkeypatch, obligation, [record])["status"]

        blocked = dominated and evidence_class == "AGENT_JUDGMENT"
        assert (status == "VERIFIED") == (not blocked)


@settings(max_examples=100, deadline=None)
@given(results=st.lists(RESULTS, min_size=1, max_size=4))
def test_a_resolution_is_always_one_of_the_declared_states(results: list[str]) -> None:
    with pytest.MonkeyPatch.context() as monkeypatch:
        records = [_evidence(f"E{i}", "V1", result) for i, result in enumerate(results)]
        assert _resolve(monkeypatch, _obligation(), records)["status"] in model.STATUSES


@settings(max_examples=100, deadline=None)
@given(results=st.lists(RESULTS, min_size=0, max_size=4))
def test_unknown_is_never_treated_as_resolved(results: list[str]) -> None:
    with pytest.MonkeyPatch.context() as monkeypatch:
        records = [_evidence(f"E{i}", "V1", result) for i, result in enumerate(results)]
        resolution = _resolve(monkeypatch, _obligation(), records)
        if resolution["status"] == "UNKNOWN":
            assert resolution["status"] not in model.RESOLVED


# --- monotonicity invariants ----------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(
    left=CRITICALITIES,
    right=CRITICALITIES,
    mandatory=st.booleans(),
    candidate_mandatory=st.booleans(),
    enforced=st.booleans(),
    candidate_enforced=st.booleans(),
    capabilities=st.lists(CAPABILITIES, min_size=0, max_size=4),
    candidate_capabilities=st.lists(CAPABILITIES, min_size=0, max_size=4),
    depth=st.integers(min_value=1, max_value=4),
    candidate_depth=st.integers(min_value=1, max_value=4),
)
def test_merging_a_recompiled_obligation_can_only_ask_for_the_same_or_more(
    left: str,
    right: str,
    mandatory: bool,
    candidate_mandatory: bool,
    enforced: bool,
    candidate_enforced: bool,
    capabilities: list[str],
    candidate_capabilities: list[str],
    depth: int,
    candidate_depth: int,
) -> None:
    previous = _obligation(
        criticality=left,
        mandatory=mandatory,
        enforced=enforced,
        acceptable_proof_capabilities=sorted(set(capabilities)),
        floor=depth,
        level=depth,
    )
    candidate = _obligation(
        criticality=right,
        mandatory=candidate_mandatory,
        enforced=candidate_enforced,
        acceptable_proof_capabilities=sorted(set(candidate_capabilities)),
        level=candidate_depth,
    )

    merged = model.monotonic(previous, candidate)

    assert model.CRITICALITY.index(merged["criticality"]) >= model.CRITICALITY.index(left)
    assert merged["mandatory"] >= previous["mandatory"]
    assert merged["enforced"] >= previous["enforced"]
    assert set(merged["acceptable_proof_capabilities"]) >= set(
        previous["acceptable_proof_capabilities"]
    )
    assert model.depth(merged) >= model.depth(previous)
    # Whatever the merge produced, it is never itself a contraction of what was stored.
    assert model.contraction(previous, merged) == []


@settings(max_examples=200, deadline=None)
@given(left=CRITICALITIES, right=CRITICALITIES)
def test_the_stronger_criticality_is_the_one_that_survives(left: str, right: str) -> None:
    result = model.stronger(left, right)
    assert result in {left, right}
    assert model.CRITICALITY.index(result) == max(
        model.CRITICALITY.index(left), model.CRITICALITY.index(right)
    )


@settings(max_examples=100, deadline=None)
@given(
    first=st.lists(st.text(min_size=1, max_size=6), min_size=1, max_size=4, unique=True),
    extra=st.lists(st.text(min_size=1, max_size=6), min_size=1, max_size=3, unique=True),
)
def test_more_observed_impact_never_narrows_an_obligation(
    first: list[str], extra: list[str]
) -> None:
    assume(not set(first) & set(extra))
    previous = _obligation(affected_paths=sorted(first))
    merged = model.monotonic(previous, _obligation(affected_paths=sorted(first + extra)))
    assert set(merged["affected_paths"]) == set(first) | set(extra)
    assert set(merged["affected_paths"]) >= set(previous["affected_paths"])


# --- registry invariants --------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(capability=CAPABILITIES)
def test_every_capability_a_deterministic_verifier_supplies_is_reported_as_such(
    capability: str,
) -> None:
    known = Registry()
    suppliers = known.supplying(capability)
    assert (capability in known.deterministic_capabilities()) == any(
        e["deterministic"] for e in suppliers
    )


@settings(max_examples=100, deadline=None)
@given(kind=st.text(min_size=1, max_size=8))
def test_an_unknown_kind_never_gains_a_capability_it_did_not_declare(kind: str) -> None:
    known = Registry()
    assume(kind not in known.entries)
    assert known.capabilities(kind) == set()
