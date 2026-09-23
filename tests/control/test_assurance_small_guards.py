"""Small guards with large consequences: the recorded schema, legacy evidence, identity.

The schema version decides whether the engine governs a project at all, so what is on disk
has to be what the plane says. Legacy evidence of a kind nobody declared must not be
promoted to deterministic proof. And a record that carries a secret, or an identifier of
the wrong kind, is refused rather than stored or acted on.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from assurance_support import claimed, contract, sources

from agentic_discipline.control.assurance import impact, migration, model, service
from agentic_discipline.control.contracts import ControlError
from agentic_discipline.control.plane import Plane, adopt
from agentic_discipline.control.store import Store


@pytest.fixture
def plane(tmp_path: Path) -> Any:
    sources(tmp_path, {"src/report.py": "value = 1\n"})
    adopt(tmp_path)
    with Plane(tmp_path) as opened:
        yield opened


def _on_disk(plane: Any) -> int:
    """The schema version as a fresh reader of the database file sees it."""

    reader = Store(Path(plane.root) / ".agentic" / "control" / "state.db")
    try:
        return int(reader.schema_version)
    finally:
        reader.close()


def test_migration_and_rollback_write_the_schema_version_to_disk(plane: Any) -> None:
    from agentic_discipline.control.assurance.migration import _set_version

    _set_version(plane, "1")
    assert _on_disk(plane) == 1

    applied = migration.migrate(plane)
    assert _on_disk(plane) == 2

    migration.rollback(plane, applied["migration_id"], "later")
    assert _on_disk(plane) == 1


def test_legacy_evidence_of_an_undeclared_kind_is_classified_as_measured(plane: Any) -> None:
    """A kind nobody declared makes no promise about determinism, so it is not given one."""

    task, _ = claimed(plane, contract())
    with plane.store.transaction():
        plane.store.put(
            "evidence",
            {
                "task_id": task,
                "kind": "someones-custom-check",
                "verifier": "V",
                "acceptance": [0],
                "result": "PASS",
                "exit_code": 0,
                "command": ["pytest", "-q", "tests/test_custom.py"],
            },
        )

    migration.migrate(plane)

    (legacy,) = [e for e in plane.store.list("evidence") if e["kind"] == "someones-custom-check"]
    assert (legacy["evidence_class"], legacy["assurance_provenance"]) == ("MEASURED", "LEGACY")


def test_rollback_refuses_an_identifier_that_is_not_a_migration(plane: Any) -> None:
    task, _ = claimed(plane, contract())

    with pytest.raises(ControlError, match=f"^Record not found: {task}$"):
        migration.rollback(plane, task, "later")


def test_an_obligation_carrying_a_secret_is_refused(plane: Any) -> None:
    task, _ = claimed(plane, contract())
    service.compile_plan(plane, task, phase="INITIAL")
    obligation = service.obligations_for(plane, task)[0]
    fields = {key: obligation[key] for key in model.FIELDS}

    model.obligation_contract(fields)
    with pytest.raises(ControlError, match="Store secret references, not values"):
        model.obligation_contract({**fields, "origin": {**fields["origin"], "password": "x"}})


def test_the_stronger_criticality_wins_and_a_tie_is_itself() -> None:
    assert model.stronger("LOW", "CRITICAL") == "CRITICAL"
    assert model.stronger("HIGH", "STANDARD") == "HIGH"
    assert model.stronger("HIGH", "HIGH") == "HIGH"


def test_a_scope_is_matched_by_its_exact_directory_name() -> None:
    """Whatever characters a directory name ends in, the name is matched whole."""

    assert impact.in_scope("BOX/items.py", ["BOX"]) is True
    assert impact.in_scope("BOX/items.py", ["BOX/"]) is True
    assert impact.in_scope("BO/items.py", ["BOX"]) is False
    assert impact.in_scope("anything.py", ["."]) is True
