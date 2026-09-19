"""Make text I/O without an explicit encoding behave as on Windows.

Python falls back to the locale's encoding when a file is opened, read or written
without `encoding`, and when a subprocess is read as text without one. On Windows
that locale is a legacy code page (cp1252 in the default Western setup), so UTF-8
text read that way comes back garbled and non-ASCII text is written in the wrong
encoding. Linux, where the suite usually runs, defaults to UTF-8 and even turns a
`C` locale into UTF-8 mode, so it can never show the difference.

`use_legacy_code_page` patches the few entry points the package uses so that a
missing encoding means cp1252 there too. Calls that pass an encoding are untouched.
"""

from __future__ import annotations

import pathlib
import subprocess
from typing import Any

import pytest

LEGACY = "cp1252"


def use_legacy_code_page(monkeypatch: pytest.MonkeyPatch) -> None:
    read_text = pathlib.Path.read_text
    write_text = pathlib.Path.write_text
    path_open = pathlib.Path.open
    run = subprocess.run

    def legacy_read_text(self: pathlib.Path, *args: Any, **kwargs: Any) -> str:
        if not args and kwargs.get("encoding") is None:
            kwargs["encoding"] = LEGACY
        return read_text(self, *args, **kwargs)

    def legacy_write_text(self: pathlib.Path, data: str, *args: Any, **kwargs: Any) -> int:
        if not args and kwargs.get("encoding") is None:
            kwargs["encoding"] = LEGACY
        return write_text(self, data, *args, **kwargs)

    def legacy_open(self: pathlib.Path, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if "b" not in mode and len(args) < 2 and kwargs.get("encoding") is None:
            kwargs["encoding"] = LEGACY
        return path_open(self, mode, *args, **kwargs)

    def legacy_run(*args: Any, **kwargs: Any) -> Any:
        textual = kwargs.get("text") or kwargs.get("universal_newlines") or kwargs.get("errors")
        if textual and kwargs.get("encoding") is None:
            kwargs["encoding"] = LEGACY
        return run(*args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "read_text", legacy_read_text)
    monkeypatch.setattr(pathlib.Path, "write_text", legacy_write_text)
    monkeypatch.setattr(pathlib.Path, "open", legacy_open)
    monkeypatch.setattr(subprocess, "run", legacy_run)
