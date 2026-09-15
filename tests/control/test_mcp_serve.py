"""MCP stdio loop framing, line by line.

`serve` reads JSON-RPC messages one line at a time from an agent over stdio. The
existing tests exchanged a few valid messages, so the size limit, the recovery after
an oversized or malformed line, or when a response is written and flushed could
change unnoticed. The session is recorded so each case pins exactly what the loop
reads, answers and writes.
"""

from __future__ import annotations

import io
import json
from typing import Any

import pytest

from agentic_discipline.control import mcp
from agentic_discipline.control.contracts import encode
from agentic_discipline.control.mcp import MAX_MESSAGE, serve


class _Sink(io.StringIO):
    def __init__(self) -> None:
        super().__init__()
        self.flushes: list[str] = []

    def flush(self) -> None:
        self.flushes.append(self.getvalue())
        super().flush()


@pytest.fixture
def received(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    seen: list[Any] = []

    def receive(self: Any, message: Any) -> dict[str, Any] | None:
        seen.append((self.plane, message))
        if isinstance(message, dict) and message.get("notify"):
            return None
        return {
            "jsonrpc": "2.0",
            "id": message.get("id") if isinstance(message, dict) else None,
            "result": "ok",
        }

    monkeypatch.setattr(mcp.Session, "receive", receive)
    return seen


def _error(code: int, message: str) -> str:
    return (
        encode({"jsonrpc": "2.0", "id": None, "error": {"code": code, "message": message}}) + "\n"
    )


def _ok(identifier: Any) -> str:
    return encode({"jsonrpc": "2.0", "id": identifier, "result": "ok"}) + "\n"


def test_each_message_gets_one_flushed_response_and_notifications_get_none(
    received: list[Any],
) -> None:
    plane = object()
    source = io.StringIO('{"id": 1}\n{"id": 2, "notify": true}\n{"id": 3}')
    sink = _Sink()

    serve(plane, source, sink)

    assert received == [(plane, {"id": 1}), (plane, {"id": 2, "notify": True}), (plane, {"id": 3})]
    assert sink.getvalue() == _ok(1) + _ok(3)
    assert sink.flushes == [_ok(1), _ok(1) + _ok(3)]


@pytest.mark.parametrize(
    "line",
    ["not json\n", '{"id": 1\n', "[" * 100000 + "\n"],
    ids=["text", "truncated", "deep-nesting"],
)
def test_malformed_json_is_answered_and_the_loop_continues(received: list[Any], line: str) -> None:
    sink = _Sink()
    serve(object(), io.StringIO(line + '{"id": 9}\n'), sink)
    assert sink.getvalue() == _error(-32700, "Invalid JSON") + _ok(9)
    assert [message for _, message in received] == [{"id": 9}]


def test_oversized_messages_are_skipped_to_their_end_and_refused(received: list[Any]) -> None:
    oversized = "x" * (MAX_MESSAGE * 2 + 10) + "\n"
    sink = _Sink()
    serve(object(), io.StringIO(oversized + '{"id": 5}\n'), sink)
    assert sink.getvalue() == _error(-32600, "Message exceeds size limit") + _ok(5)
    assert [message for _, message in received] == [{"id": 5}]


def test_a_message_of_exactly_the_limit_is_accepted(received: list[Any]) -> None:
    prefix, suffix = '{"id": 7, "pad": "', '"}\n'
    line = prefix + "p" * (MAX_MESSAGE - len(prefix) - len(suffix)) + suffix
    assert len(line) == MAX_MESSAGE
    sink = _Sink()
    serve(object(), io.StringIO(line), sink)
    assert sink.getvalue() == _ok(7)
    assert json.loads(line) == received[0][1]


def test_an_oversized_final_message_without_newline_ends_the_loop(received: list[Any]) -> None:
    sink = _Sink()
    serve(object(), io.StringIO("y" * (MAX_MESSAGE + 1)), sink)
    assert sink.getvalue() == _error(-32600, "Message exceeds size limit")
    assert received == []


def test_empty_input_ends_without_output(received: list[Any]) -> None:
    sink = _Sink()
    serve(object(), io.StringIO(""), sink)
    assert (sink.getvalue(), sink.flushes, received) == ("", [], [])
