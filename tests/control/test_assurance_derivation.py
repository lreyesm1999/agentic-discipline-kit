"""What an obligation carries from its task, and what evidence may speak for it.

An obligation is only as traceable as the provenance it records: the requirements, the
architecture boundaries and the capabilities its verifiers supply. And evidence recorded
before obligations existed still has to count for the criterion it was recorded against.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from assurance_support import claimed, contract, sources, spec

from agentic_discipline.control.assurance import compiler, resolver, service
from agentic_discipline.control.contracts import ControlError
from agentic_discipline.control.plane import Plane, adopt


@pytest.fixture
def plane(tmp_path: Path) -> Any:
    sources(tmp_path, {"src/report.py": "value = 1\n"})
    adopt(tmp_path)
    with Plane(tmp_path) as opened:
        yield opened


def _requirement(plane: Any) -> str:
    return str(
        plane.knowledge.apply(
            [
                {
                    "graph": "requirement",
                    "type": "requirement",
                    "name": "Reports stay correct",
                    "source_ref": "specs/requirements.md",
                    "authority": "human",
                    "confidence": 1,
                    "observation": "DECLARED",
                }
            ],
            plane.store.knowledge_version,
            "approved requirement",
        )["entities"][0]["id"]
    )


def _by(plane: Any, task: str, derivation: str) -> list[dict[str, Any]]:
    return [o for o in service.obligations_for(plane, task) if o["derivation"] == derivation]


def test_a_criterion_two_verifiers_cover_accepts_what_either_supplies(plane: Any) -> None:
    task, _ = claimed(plane, contract(verification=[spec("unit", [0]), spec("property", [0])]))
    service.compile_plan(plane, task, phase="INITIAL")
    known = service.registry_for(plane)

    (obligation,) = _by(plane, task, "CONTRACT")

    assert set(obligation["acceptable_proof_capabilities"]) == (
        known.capabilities("unit") | known.capabilities("property")
    )


def test_obligations_carry_the_task_s_requirements_and_boundaries(plane: Any) -> None:
    requirement = _requirement(plane)
    task, _ = claimed(
        plane,
        contract(
            requirements=[requirement], boundaries=["report API", "value API"], risk="CRITICAL"
        ),
    )
    service.compile_plan(plane, task, phase="INITIAL")

    (criterion,) = _by(plane, task, "CONTRACT")
    assert criterion["origin"]["requirement_ids"] == [requirement]
    assert criterion["origin"]["architecture_ids"] == ["report API", "value API"]
    policies = _by(plane, task, "POLICY")
    human = [o for o in policies if o["origin"]["policy_ids"] == ["HUMAN-ACCEPTANCE"]]
    strength = [o for o in policies if o["origin"]["policy_ids"] == ["TEST-STRENGTH"]]
    assert len(human) == len(strength) == 1
    assert human[0]["origin"]["requirement_ids"] == [requirement]
    assert strength[0]["origin"]["requirement_ids"] == [requirement]
    # The human and the falsification claims about one task are two records, not one.
    assert human[0]["id"] != strength[0]["id"]


def test_an_obligation_without_an_origin_key_is_refused() -> None:
    with pytest.raises(ControlError, match="^An obligation needs an origin key$") as refused:
        compiler._obligation(
            {"id": "TASK-1"},
            origin_key="",
            claim="x",
            capabilities=["unit"],
            criticality="LOW",
            derivation="CONTRACT",
            reason="y",
            paths=["src"],
            phase="INITIAL",
            enforced=True,
        )
    assert refused.value.code == "INVALID_OBLIGATION"


def test_risk_signals_are_read_one_path_at_a_time() -> None:
    assert compiler.signals(["src/auth/login.py", "docs/readme.md"]) == ["auth"]
    assert compiler.signals(["SRC/AUTH/LOGIN.PY"]) == ["auth"]
    assert compiler.signals([]) == []


def _contract_obligation(**origin: Any) -> dict[str, Any]:
    return {
        "id": "PO-1",
        "derivation": "CONTRACT",
        "origin": {"acceptance_ids": [0], **origin},
    }


def test_evidence_recorded_before_obligations_existed_still_counts_for_its_criterion() -> None:
    """2.0 evidence names the criteria it proves and no obligation, and it must still count."""

    legacy = {"acceptance": [0]}

    assert resolver.matches(legacy, _contract_obligation()) is True
    assert resolver.matches({"acceptance": [1]}, _contract_obligation()) is False
    # Only a contract claim is proven by criterion; a policy claim needs its own evidence.
    policy = {**_contract_obligation(), "derivation": "POLICY"}
    assert resolver.matches(legacy, policy) is False
    assert resolver.matches({"acceptance": [], "obligation_ids": ["PO-1"]}, policy) is True


def test_the_binding_moves_when_the_criteria_an_obligation_proves_move(plane: Any) -> None:
    task_id, _ = claimed(
        plane,
        contract(
            acceptance=["The reported value is one", "The report is written once"],
            verification=[spec("unit", [0, 1])],
        ),
    )
    service.compile_plan(plane, task_id, phase="INITIAL")
    task = plane.store.get(task_id, "task")
    first = next(o for o in _by(plane, task_id, "CONTRACT") if o["origin"]["acceptance_ids"] == [0])

    other = {**first, "origin": {**first["origin"], "acceptance_ids": [1]}}

    assert resolver.obligation_binding(plane, task, first) != resolver.obligation_binding(
        plane, task, other
    )
