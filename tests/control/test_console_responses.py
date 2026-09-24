"""Localhost console responses, header by header.

The console is the only network surface of the control plane. The existing test
requested each route and checked status codes, so a response could lose its
security headers, serve the wrong asset, accept a foreign Host header on a
different port, or leak a crash instead of 503 without failing. Each case reads
the full response.
"""

from __future__ import annotations

import http.client
import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline.control.api import call
from agentic_discipline.control.console import CSS, HTML, JS, server
from agentic_discipline.control.contracts import encode

SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'; base-uri 'none'",
}
DEFAULT_HOST = object()


@contextmanager
def _serving(root: Path) -> Iterator[int]:
    web = server(root, 0)
    worker = threading.Thread(target=web.serve_forever, daemon=True)
    worker.start()
    try:
        yield web.server_port
    finally:
        web.shutdown()
        web.server_close()
        worker.join()


def _get(port: int, path: str, host: Any = DEFAULT_HOST) -> tuple[int, str, dict[str, str], bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        if host is DEFAULT_HOST:
            connection.request("GET", path)
        else:
            connection.putrequest("GET", path, skip_host=True)
            if host is not None:
                connection.putheader("Host", host)
            connection.endheaders()
        response = connection.getresponse()
        body = response.read()
        return response.status, response.reason, dict(response.getheaders()), body
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("path", "content", "mime"),
    [
        ("/", HTML, "text/html"),
        ("/app.css", CSS, "text/css"),
        ("/app.js", JS, "text/javascript"),
        ("/app.css?v=2", CSS, "text/css"),
    ],
)
def test_static_assets_are_served_with_security_headers(
    project: Any, path: str, content: str, mime: str
) -> None:
    with _serving(project.root) as port:
        status, _, headers, body = _get(port, path)
    assert (status, body) == (200, content.encode("utf-8"))
    assert {key: headers[key] for key in (*SECURITY_HEADERS, "Content-Type", "Content-Length")} == {
        **SECURITY_HEADERS,
        "Content-Type": f"{mime}; charset=utf-8",
        "Content-Length": str(len(body)),
    }


@pytest.mark.parametrize(
    ("path", "operation"),
    [
        ("/api/status", "status"),
        ("/api/timeline", "timeline"),
        ("/api/assurance", "assurance_status"),
    ],
)
def test_api_routes_return_the_versioned_read_operation(
    project: Any, path: str, operation: str
) -> None:
    with _serving(project.root) as port:
        status, _, headers, body = _get(port, path)
    expected = json.loads(encode(call(project, operation, {})))
    assert (status, json.loads(body)) == (200, expected)
    assert expected["operation"] == operation
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    assert headers["Content-Length"] == str(len(body))
    assert {key: headers[key] for key in SECURITY_HEADERS} == SECURITY_HEADERS


def test_only_this_ports_loopback_names_are_accepted(project: Any) -> None:
    with _serving(project.root) as port:
        for host in (f"127.0.0.1:{port}", f"localhost:{port}"):
            assert _get(port, "/", host)[0] == 200, host
        for host in (
            None,
            "localhost",
            "127.0.0.1",
            f"localhost:{port + 1}",
            f"attacker.example:{port}",
            "attacker.example",
        ):
            status, _, _, body = _get(port, "/api/status", host)
            assert status == 403, host
            assert b"project" not in body


@pytest.mark.parametrize("path", ["/api/other", "/app.js/extra", "/index.html", "/api/status/"])
def test_unknown_routes_are_not_found(project: Any, path: str) -> None:
    with _serving(project.root) as port:
        assert _get(port, path)[0] == 404


@pytest.mark.parametrize("state", ["missing", "corrupt"])
def test_unavailable_project_state_is_a_503_not_a_crash(tmp_path: Path, state: str) -> None:
    root = tmp_path / "project"
    root.mkdir()
    if state == "corrupt":
        database = root / ".agentic" / "control" / "state.db"
        database.parent.mkdir(parents=True)
        database.write_bytes(b"this is not a sqlite database" * 10)
    with _serving(root) as port:
        for path in ("/api/status", "/api/timeline"):
            status, reason, _, _ = _get(port, path)
            assert (status, reason) == (503, "Project state unavailable")
        # Static assets do not depend on project state.
        assert _get(port, "/")[0] == 200


def test_requests_are_never_logged(project: Any, capfd: pytest.CaptureFixture[str]) -> None:
    with _serving(project.root) as port:
        for path, host in (
            ("/", DEFAULT_HOST),
            ("/missing", DEFAULT_HOST),
            ("/", "attacker.example"),
        ):
            _get(port, path, host)
    assert capfd.readouterr().err == ""


def test_server_binds_loopback_on_the_documented_default_port(project: Any) -> None:
    from agentic_discipline.control.cli import parser

    assert parser().parse_args(["console"]).port == 8765
    web = server(project.root, 0)
    try:
        assert web.server_address[0] == "127.0.0.1"
    finally:
        web.server_close()


def test_only_the_first_question_mark_starts_the_query(project: Any) -> None:
    with _serving(project.root) as port:
        assert _get(port, "/api/status?view=1?extra=2")[0] == 200
