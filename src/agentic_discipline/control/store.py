"""SQLite unit of work, optimistic records, typed links and tamper-evident history."""

from __future__ import annotations

import builtins
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .contracts import digest, encode, require, safe_data, uid

# Schema 1 is Agentic Discipline 2.0. Schema 2 adds the assurance engine and is reached
# only through the explicit `agentic assurance migrate`, so a 2.0 project keeps its
# behaviour until an owner upgrades it.
SUPPORTED_VERSIONS = ("1", "2")
CURRENT_VERSION = "2"
SCHEMA = (
    "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    f"INSERT INTO meta VALUES ('schema_version','{CURRENT_VERSION}'),('knowledge_version','0')",
    "CREATE TABLE records (id TEXT PRIMARY KEY, kind TEXT NOT NULL, version INTEGER NOT NULL, payload TEXT NOT NULL)",
    "CREATE INDEX records_kind ON records(kind)",
    "CREATE TABLE revisions (id TEXT NOT NULL, version INTEGER NOT NULL, payload TEXT NOT NULL, knowledge_version INTEGER NOT NULL, PRIMARY KEY(id,version))",
    "CREATE TABLE edges (id TEXT PRIMARY KEY, source TEXT NOT NULL REFERENCES records(id), target TEXT NOT NULL REFERENCES records(id), relation TEXT NOT NULL, UNIQUE(source,target,relation))",
    "CREATE INDEX edge_source ON edges(source,relation)",
    "CREATE INDEX edge_target ON edges(target,relation)",
    "CREATE VIRTUAL TABLE search USING fts5(id UNINDEXED, content)",
    "CREATE TABLE events (seq INTEGER PRIMARY KEY, timestamp REAL NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, payload TEXT NOT NULL, previous_hash TEXT, hash TEXT NOT NULL)",
    "CREATE TRIGGER events_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'append-only audit'); END",
    "CREATE TRIGGER events_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'append-only audit'); END",
)


class Store:
    def __init__(self, path: Path, *, create: bool = False) -> None:
        require(create or path.is_file(), "NOT_ADOPTED", "Run agentic adopt first")
        require(not path.is_symlink(), "INVALID_PATH", "Database must not be a symlink")
        if create:
            path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.db = sqlite3.connect(path, timeout=5, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=5000")
        if not self.db.execute("SELECT name FROM sqlite_master WHERE name='meta'").fetchone():
            try:
                with self.transaction():
                    for statement in SCHEMA:
                        self.db.execute(statement)
            except BaseException:
                self.db.close()
                raise
        row = self.db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        require(
            row is not None and row[0] in SUPPORTED_VERSIONS,
            "SCHEMA_VERSION",
            "Unsupported database version; restore or upgrade explicitly",
        )
        self.schema_version = int(row[0])

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        require(not self.db.in_transaction, "NESTED_TRANSACTION", "Transaction already open")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            yield
            self.db.execute("COMMIT")
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    @property
    def knowledge_version(self) -> int:
        return int(
            self.db.execute("SELECT value FROM meta WHERE key='knowledge_version'").fetchone()[0]
        )

    def bump(self) -> int:
        require(
            self.db.in_transaction, "TRANSACTION_REQUIRED", "Knowledge write needs a transaction"
        )
        value = self.knowledge_version + 1
        self.db.execute("UPDATE meta SET value=? WHERE key='knowledge_version'", (str(value),))
        return value

    def get(self, identifier: str, kind: str | None = None) -> dict[str, Any]:
        row = self.db.execute("SELECT * FROM records WHERE id=?", (identifier,)).fetchone()
        require(
            row is not None and (kind is None or row["kind"] == kind),
            "NOT_FOUND",
            f"Record not found: {identifier}",
        )
        return {**json.loads(row["payload"]), "id": row["id"], "version": row["version"]}

    def list(self, kind: str) -> builtins.list[dict[str, Any]]:
        return [
            {**json.loads(r["payload"]), "id": r["id"], "version": r["version"]}
            for r in self.db.execute("SELECT * FROM records WHERE kind=? ORDER BY id", (kind,))
        ]

    def put(
        self, kind: str, data: dict[str, Any], *, expected: int | None = None, actor: str = "local"
    ) -> dict[str, Any]:
        require(self.db.in_transaction, "TRANSACTION_REQUIRED", "Record write needs a transaction")
        safe_data(data)
        identifier = data.get("id") or uid(kind.upper()[:4])
        current = self.db.execute(
            "SELECT version,kind FROM records WHERE id=?", (identifier,)
        ).fetchone()
        if current:
            require(
                current[1] == kind and current[0] == expected,
                "VERSION_CONFLICT",
                f"Concurrent write to {identifier}",
            )
        else:
            require(expected is None, "VERSION_CONFLICT", "Expected record does not exist")
        version = (current[0] if current else 0) + 1
        payload = {k: v for k, v in data.items() if k not in {"id", "version"}}
        raw = encode(payload)
        self.db.execute(
            "INSERT INTO records VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,payload=excluded.payload",
            (identifier, kind, version, raw),
        )
        self.db.execute(
            "INSERT INTO revisions VALUES (?,?,?,?)",
            (identifier, version, raw, self.knowledge_version),
        )
        if kind == "entity":
            self.db.execute("DELETE FROM search WHERE id=?", (identifier,))
            self.db.execute("INSERT INTO search VALUES (?,?)", (identifier, raw))
        self.event(
            actor,
            f"{kind}.write",
            {"id": identifier, "version": version, "payload_hash": digest(payload)},
        )
        return {**payload, "id": identifier, "version": version}

    def event(self, actor: str, action: str, data: dict[str, Any]) -> None:
        require(self.db.in_transaction, "TRANSACTION_REQUIRED", "Audit write needs a transaction")
        safe_data(data)
        row = self.db.execute("SELECT seq,hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        record = {
            "seq": row[0] + 1 if row else 1,
            "timestamp": time.time(),
            "actor": actor,
            "action": action,
            "payload": data,
            "previous_hash": row[1] if row else None,
        }
        self.db.execute(
            "INSERT INTO events VALUES (?,?,?,?,?,?,?)",
            (
                record["seq"],
                record["timestamp"],
                actor,
                action,
                encode(data),
                record["previous_hash"],
                digest(record),
            ),
        )

    def audit(self) -> dict[str, Any]:
        previous = None
        count = 0
        for row in self.db.execute("SELECT * FROM events ORDER BY seq"):
            count += 1
            record = dict(row)
            claimed = record.pop("hash")
            record["payload"] = json.loads(record["payload"])
            require(
                record["seq"] == count
                and record["previous_hash"] == previous
                and digest(record) == claimed,
                "AUDIT_CORRUPT",
                "Audit chain does not match",
            )
            previous = claimed
        return {"records": count, "head_hash": previous, "status": "PASS" if count else "UNKNOWN"}

    def history(self, identifier: str) -> builtins.list[dict[str, Any]]:
        self.get(identifier)
        return [
            {
                "id": identifier,
                "version": r["version"],
                "knowledge_version": r["knowledge_version"],
                "payload": json.loads(r["payload"]),
            }
            for r in self.db.execute(
                "SELECT * FROM revisions WHERE id=? ORDER BY version", (identifier,)
            )
        ]

    def entities_at(self, knowledge_version: int) -> builtins.list[dict[str, Any]]:
        return [
            {**json.loads(row["payload"]), "id": row["id"], "version": row["version"]}
            for row in self.db.execute(
                "SELECT h.* FROM revisions h JOIN records r ON r.id=h.id WHERE r.kind='entity' AND h.version=(SELECT MAX(v.version) FROM revisions v WHERE v.id=h.id AND v.knowledge_version<=?) ORDER BY h.id",
                (knowledge_version,),
            )
        ]

    def timeline(
        self, identifier: str | None = None, limit: int = 100
    ) -> builtins.list[dict[str, Any]]:
        require(1 <= limit <= 1000, "INVALID_LIMIT", "Limit must be 1..1000")
        rows = self.db.execute("SELECT * FROM events ORDER BY seq DESC LIMIT ?", (limit,))
        return [
            {**dict(r), "payload": json.loads(r["payload"])}
            for r in rows
            if identifier is None or identifier in r["payload"] or identifier == r["actor"]
        ]

    def backup(self, target: Path) -> None:
        require(not target.exists(), "ALREADY_EXISTS", "Backup destination already exists")
        with sqlite3.connect(target) as other:
            self.db.backup(other)
        target.chmod(0o600)
