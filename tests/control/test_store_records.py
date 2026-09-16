"""SQLite store, row by row.

Every control-plane record, revision, search entry and audit event passes through the
store. Existing tests exercised it through the plane, so a revision could carry the
wrong knowledge version, an audit event could lose its chain link, or a failed schema
creation could leave a half-built database without failing anything. Each case reads
the rows the store wrote.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline.control import store as store_module
from agentic_discipline.control.contracts import ControlError, digest, encode
from agentic_discipline.control.store import Store

TABLES = {
    "meta",
    "records",
    "records_kind",
    "revisions",
    "edges",
    "edge_source",
    "edge_target",
    "search",
    "events",
    "events_no_update",
    "events_no_delete",
}


def _rejects(code: str, message: str, action: Any, *args: Any, **kwargs: Any) -> None:
    with pytest.raises(ControlError) as caught:
        action(*args, **kwargs)
    assert (caught.value.code, str(caught.value)) == (code, message)


def _put(store: Store, kind: str, data: dict[str, Any], **options: Any) -> dict[str, Any]:
    with store.transaction():
        return store.put(kind, data, **options)


def _rows(store: Store, sql: str, *parameters: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in store.db.execute(sql, parameters)]


@pytest.fixture
def store(tmp_path: Path) -> Any:
    with Store(tmp_path / "state.db", create=True) as opened:
        yield opened


# --- opening --------------------------------------------------------------------------------


def test_missing_database_is_not_created_without_adoption(tmp_path: Path) -> None:
    path = tmp_path / "state.db"
    _rejects("NOT_ADOPTED", "Run agentic adopt first", Store, path)
    assert not path.exists()


def test_new_database_gets_the_schema_and_connection_settings(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "state" / "state.db"
    with Store(path, create=True) as store:
        assert store.path == path
        assert store.db.isolation_level is None
        names = {row["name"] for row in store.db.execute("SELECT name FROM sqlite_master")}
        assert TABLES <= names
        assert _rows(store, "SELECT * FROM meta ORDER BY key") == [
            {"key": "knowledge_version", "value": "0"},
            {"key": "schema_version", "value": "1"},
        ]
        assert store.db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert store.db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert store.db.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_reopening_keeps_existing_state(tmp_path: Path) -> None:
    path = tmp_path / "state.db"
    with Store(path, create=True) as store:
        with store.transaction():
            store.bump()
    with Store(path) as store:
        assert store.knowledge_version == 1


@pytest.mark.parametrize(
    "change",
    [
        "UPDATE meta SET value='2' WHERE key='schema_version'",
        "DELETE FROM meta WHERE key='schema_version'",
    ],
)
def test_unsupported_schema_versions_are_refused(tmp_path: Path, change: str) -> None:
    path = tmp_path / "state.db"
    with Store(path, create=True) as store:
        store.db.execute(change)
    _rejects(
        "SCHEMA_VERSION", "Unsupported database version; restore or upgrade explicitly", Store, path
    )


def test_failed_schema_creation_leaves_no_partial_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "state.db"
    monkeypatch.setattr(store_module, "SCHEMA", ("CREATE TABLE meta (key TEXT)", "NOT SQL"))
    with pytest.raises(sqlite3.OperationalError):
        Store(path, create=True)
    with closing(sqlite3.connect(path)) as raw:
        assert raw.execute("SELECT name FROM sqlite_master").fetchall() == []
    # The store closed its connection, so the file can be removed even on Windows.
    path.unlink()


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlinks")
def test_symlinked_database_is_refused(tmp_path: Path) -> None:
    real = tmp_path / "real.db"
    Store(real, create=True).close()
    link = tmp_path / "state.db"
    link.symlink_to(real)
    _rejects("INVALID_PATH", "Database must not be a symlink", Store, link)


# --- transactions ---------------------------------------------------------------------------


def test_transactions_commit_roll_back_and_do_not_nest(store: Store, tmp_path: Path) -> None:
    with store.transaction():
        _rejects("NESTED_TRANSACTION", "Transaction already open", store.transaction().__enter__)
        store.bump()
    with pytest.raises(RuntimeError, match="stop"):
        with store.transaction():
            store.bump()
            raise RuntimeError("stop")
    assert not store.db.in_transaction
    with sqlite3.connect(tmp_path / "state.db") as other:
        value = other.execute("SELECT value FROM meta WHERE key='knowledge_version'").fetchone()
    assert value == ("1",)


def test_writes_require_a_transaction(store: Store) -> None:
    _rejects("TRANSACTION_REQUIRED", "Record write needs a transaction", store.put, "task", {})
    _rejects("TRANSACTION_REQUIRED", "Knowledge write needs a transaction", store.bump)
    _rejects("TRANSACTION_REQUIRED", "Audit write needs a transaction", store.event, "a", "b", {})


# --- records --------------------------------------------------------------------------------


def test_new_record_row_revision_and_event(store: Store) -> None:
    with store.transaction():
        store.bump()
        record = store.put("task", {"objective": "Ship", "id": None, "version": 9}, actor="agent")

    assert record["id"].startswith("TASK-")
    assert record == {"objective": "Ship", "id": record["id"], "version": 1}
    payload = encode({"objective": "Ship"})
    assert _rows(store, "SELECT * FROM records") == [
        {"id": record["id"], "kind": "task", "version": 1, "payload": payload}
    ]
    assert _rows(store, "SELECT * FROM revisions") == [
        {"id": record["id"], "version": 1, "payload": payload, "knowledge_version": 1}
    ]
    (event,) = store.timeline()
    assert (event["actor"], event["action"], event["payload"]) == (
        "agent",
        "task.write",
        {"id": record["id"], "version": 1, "payload_hash": digest({"objective": "Ship"})},
    )
    assert _rows(store, "SELECT * FROM search") == []


def test_kind_prefix_uses_the_first_four_letters(store: Store) -> None:
    assert _put(store, "evidence", {})["id"].startswith("EVID-")
    assert _put(store, "run", {})["id"].startswith("RUN-")
    assert _put(store, "task", {"id": "TASK-given"})["id"] == "TASK-given"
    (first, *_) = store.timeline(limit=1)
    assert first["actor"] == "local"


def test_updates_add_revisions_and_keep_search_current(store: Store) -> None:
    created = _put(store, "entity", {"name": "Orders"})
    with store.transaction():
        store.bump()
        updated = store.put("entity", {**created, "name": "Invoices"}, expected=1)

    assert updated == {"name": "Invoices", "id": created["id"], "version": 2}
    assert store.get(created["id"], "entity") == updated
    assert store.history(created["id"]) == [
        {"id": created["id"], "version": 1, "knowledge_version": 0, "payload": {"name": "Orders"}},
        {
            "id": created["id"],
            "version": 2,
            "knowledge_version": 1,
            "payload": {"name": "Invoices"},
        },
    ]
    assert _rows(store, "SELECT * FROM search") == [
        {"id": created["id"], "content": encode({"name": "Invoices"})}
    ]


def test_version_and_kind_conflicts_write_nothing(store: Store) -> None:
    created = _put(store, "task", {"objective": "Ship"})
    before = (_rows(store, "SELECT * FROM records"), _rows(store, "SELECT * FROM events"))

    with store.transaction():
        _rejects(
            "VERSION_CONFLICT",
            f"Concurrent write to {created['id']}",
            store.put,
            "task",
            created,
            expected=2,
        )
        _rejects(
            "VERSION_CONFLICT",
            f"Concurrent write to {created['id']}",
            store.put,
            "entity",
            created,
            expected=1,
        )
        _rejects(
            "VERSION_CONFLICT",
            f"Concurrent write to {created['id']}",
            store.put,
            "task",
            created,
        )
        _rejects(
            "VERSION_CONFLICT",
            "Expected record does not exist",
            store.put,
            "task",
            {"id": "TASK-missing"},
            expected=1,
        )
    assert (_rows(store, "SELECT * FROM records"), _rows(store, "SELECT * FROM events")) == before


def test_records_are_read_back_by_kind(store: Store) -> None:
    task = _put(store, "task", {"id": "TASK-b"})
    other = _put(store, "task", {"id": "TASK-a"})
    _put(store, "lease", {"id": "LEAS-a"})
    assert store.list("task") == [other, task]
    _rejects("NOT_FOUND", "Record not found: TASK-a", store.get, "TASK-a", "lease")
    _rejects("NOT_FOUND", "Record not found: TASK-z", store.get, "TASK-z")
    _rejects("NOT_FOUND", "Record not found: TASK-z", store.history, "TASK-z")


def test_secrets_are_refused_before_anything_is_written(store: Store) -> None:
    with store.transaction():
        with pytest.raises(ControlError) as caught:
            store.put("task", {"note": "password=hunter2"})
        assert caught.value.code == "SECRET_REJECTED"
        with pytest.raises(ControlError) as caught:
            store.event("local", "note", {"note": "password=hunter2"})
        assert caught.value.code == "SECRET_REJECTED"
    assert _rows(store, "SELECT * FROM records") == []
    assert _rows(store, "SELECT * FROM events") == []


def test_entities_at_returns_each_entity_as_of_a_knowledge_version(store: Store) -> None:
    with store.transaction():
        store.bump()
        b = store.put("entity", {"id": "ENT-b", "name": "first"})
        a = store.put("entity", {"id": "ENT-a", "name": "only"})
        store.put("task", {"id": "TASK-a"})
    with store.transaction():
        store.bump()
        b2 = store.put("entity", {**b, "name": "second"}, expected=1)

    assert store.entities_at(0) == []
    assert store.entities_at(1) == [a, b]
    assert store.entities_at(2) == [a, b2]


# --- audit ----------------------------------------------------------------------------------


def test_events_form_a_hash_chain(store: Store) -> None:
    assert store.audit() == {"records": 0, "head_hash": None, "status": "UNKNOWN"}
    with store.transaction():
        store.event("alice", "first", {"n": 1})
        store.event("bob", "second", {"n": 2})

    first, second = _rows(store, "SELECT * FROM events ORDER BY seq")
    for row, previous in ((first, None), (second, first["hash"])):
        assert row["previous_hash"] == previous
        claimed = row.pop("hash")
        assert claimed == digest({**row, "payload": json.loads(row["payload"])})
    assert (first["seq"], second["seq"]) == (1, 2)
    head = store.db.execute("SELECT hash FROM events WHERE seq=2").fetchone()[0]
    assert store.audit() == {"records": 2, "head_hash": head, "status": "PASS"}


def test_events_cannot_be_changed_or_removed(store: Store) -> None:
    with store.transaction():
        store.event("alice", "first", {"n": 1})
    for statement in ("UPDATE events SET actor='mallory'", "DELETE FROM events"):
        with pytest.raises(sqlite3.DatabaseError, match="append-only audit"):
            store.db.execute(statement)


@pytest.mark.parametrize(
    "tamper",
    [
        "UPDATE events SET payload='{\"n\":3}' WHERE seq=2",
        "UPDATE events SET previous_hash='forged' WHERE seq=2",
        "UPDATE events SET seq=3 WHERE seq=2",
    ],
)
def test_audit_detects_a_broken_chain(store: Store, tamper: str) -> None:
    with store.transaction():
        store.event("alice", "first", {"n": 1})
        store.event("bob", "second", {"n": 2})
    store.db.execute("DROP TRIGGER events_no_update")
    store.db.execute(tamper)
    _rejects("AUDIT_CORRUPT", "Audit chain does not match", store.audit)


def test_timeline_is_newest_first_bounded_and_filtered(store: Store) -> None:
    with store.transaction():
        store.event("alice", "first", {"target": "TASK-1"})
        store.event("bob", "second", {"target": "TASK-2"})
        store.event("carol", "third", {"target": "TASK-1"})

    everything = store.timeline()
    assert [e["action"] for e in everything] == ["third", "second", "first"]
    assert set(everything[0]) == {
        "seq",
        "timestamp",
        "actor",
        "action",
        "payload",
        "previous_hash",
        "hash",
    }
    assert everything[0]["payload"] == {"target": "TASK-1"}
    assert [e["action"] for e in store.timeline(limit=2)] == ["third", "second"]
    assert [e["action"] for e in store.timeline("TASK-1")] == ["third", "first"]
    assert [e["action"] for e in store.timeline("bob")] == ["second"]
    assert len(store.timeline(limit=1)) == 1
    assert len(store.timeline(limit=1000)) == 3
    for limit in (0, 1001):
        _rejects("INVALID_LIMIT", "Limit must be 1..1000", store.timeline, limit=limit)


def test_timeline_shows_the_latest_hundred_events_by_default(store: Store) -> None:
    with store.transaction():
        for number in range(101):
            store.event("local", f"event-{number}", {})
    events = store.timeline()
    assert [e["action"] for e in events] == [f"event-{n}" for n in range(100, 0, -1)]


# --- backup ---------------------------------------------------------------------------------


def test_backup_copies_records_privately_and_never_overwrites(store: Store, tmp_path: Path) -> None:
    record = _put(store, "task", {"objective": "Ship"})
    target = tmp_path / "backup.db"

    store.backup(target)

    with Store(target) as copy:
        assert copy.list("task") == [record]
        assert copy.audit() == store.audit()
    if os.name == "posix":
        assert target.stat().st_mode & 0o777 == 0o600
    _rejects("ALREADY_EXISTS", "Backup destination already exists", store.backup, target)
