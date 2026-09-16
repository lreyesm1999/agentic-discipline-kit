"""The record an agent gets when it joins.

Every later step authenticates against this record: the session hash decides who
owns a lease, and the timestamps decide who is still alive. Existing tests call
`join` only to obtain a session token, so what it writes was never compared, and a
field could be renamed or a status written wrong without any test noticing. Each
case compares the stored record whole.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

import pytest

from agentic_discipline.control.contracts import ControlError

CAPABILITIES = ["code", "terminal"]


def test_joining_writes_the_agent_record_and_hides_the_token(project: Any) -> None:
    before = time.time()
    agent = project.join("worker", CAPABILITIES)
    after = time.time()

    assert set(agent) == {"id", "name", "session"}
    assert agent["id"].startswith("AGEN-")
    assert agent["name"] == "worker"

    record = project.store.get(agent["id"], "agent")
    assert record == {
        "id": agent["id"],
        "version": 1,
        "name": "worker",
        "capabilities": CAPABILITIES,
        "session_hash": hashlib.sha256(agent["session"].encode()).hexdigest(),
        "joined_at": record["joined_at"],
        "heartbeat_at": record["heartbeat_at"],
        "status": "ONLINE",
    }
    assert before <= record["joined_at"] <= after
    assert before <= record["heartbeat_at"] <= after
    assert agent["session"] not in str(record)


def test_the_stored_hash_is_what_authentication_matches(project: Any) -> None:
    agent = project.join("worker", CAPABILITIES)

    assert project.authenticate(agent["session"])["id"] == agent["id"]

    with pytest.raises(ControlError) as caught:
        project.authenticate(agent["session"] + "x")
    assert (caught.value.code, str(caught.value)) == ("UNAUTHORIZED", "Unknown agent session")


def test_two_agents_get_distinct_identities_and_sessions(project: Any) -> None:
    first = project.join("first", CAPABILITIES)
    second = project.join("second", ["code"])

    assert first["id"] != second["id"]
    assert first["session"] != second["session"]
    assert project.authenticate(second["session"])["capabilities"] == ["code"]
