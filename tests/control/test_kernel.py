import sqlite3
from pathlib import Path

import pytest

from agentic_discipline.control.contracts import ControlError
from agentic_discipline.control.knowledge import Knowledge
from agentic_discipline.control.store import Store


def entity(name="Orders", graph="requirement"):
    return dict(
        name=name,
        graph=graph,
        type="requirement",
        source_ref="spec.md",
        authority="contract",
        confidence=1,
        observation="DECLARED",
    )


def test_version_conflict_rollback_history_search_and_audit(tmp_path: Path):
    with Store(tmp_path / "state.db", create=True) as s:
        k = Knowledge(s)
        first = k.apply([entity()], 0, "approved requirement")["entities"][0]
        with pytest.raises(ControlError, match="Knowledge version"):
            k.apply([entity("bad")], 0, "stale")
        with pytest.raises(ControlError):
            k.apply([entity("would rollback"), {**entity(), "confidence": 9}], 1, "invalid second")
        assert s.knowledge_version == 1
        assert len(s.list("entity")) == 1
        second = k.apply([{**first, "name": "Cancellations", "expected_version": 1}], 1, "rename")[
            "entities"
        ][0]
        assert first["id"] == second["id"]
        assert len(s.history(first["id"])) == 2
        assert k.query("Cancellations")[0]["id"] == first["id"]
        k.lifecycle(first["id"], "RETIRED", "feature removed")
        assert not k.query()
        assert k.query(historical=True)
        with pytest.raises(ControlError, match="reactivated"):
            k.apply([{**second, "lifecycle": "ACTIVE", "expected_version": 3}], 3, "old docs")
        assert s.audit()["status"] == "PASS"
        with pytest.raises(sqlite3.IntegrityError):
            s.db.execute("DELETE FROM events")


def test_edge_types_provenance_and_conflicts(tmp_path: Path):
    with Store(tmp_path / "state.db", create=True) as s:
        k = Knowledge(s)
        left, right = k.apply([entity(), entity("File", "code")], 0, "baseline")["entities"]
        k.link(left["id"], right["id"], "implemented_by")
        assert k.impact(right["id"])[0]["id"] == left["id"]
        with pytest.raises(ControlError):
            k.link(left["id"], right["id"], "verified_by")
        c = dict(
            subject=left["id"],
            predicate="enabled",
            value=True,
            source_ref="old.md",
            authority="documentation",
            confidence=0.9,
            observation="DECLARED",
        )
        assert k.claim(c)["disposition"] == "CANDIDATE"
        assert k.claim({**c, "value": False, "authority": "human"})["disposition"] == "CANONICAL"
        assert len(s.list("claim")) == 2
        with pytest.raises(ControlError):
            k.claim({**c, "observation": "VERIFIED"})
