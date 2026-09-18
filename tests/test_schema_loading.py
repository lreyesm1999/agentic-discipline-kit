"""Schema lookup, JSON loading and schema error formatting.

Every contract, graph and configuration check loads a schema through these
functions, from a checkout, an installed wheel or a frozen binary. Existing tests
only exercised the checkout layout, so the lookup order, the error for a missing or
malformed document, or the location format of schema errors could change unnoticed.
Each case pins the exact candidates, value or message.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from agentic_discipline import validation
from agentic_discipline.validation import (
    ValidationError,
    _schema_candidates,
    load_json,
    load_schema,
    validate_schema,
)


class _Packaged:
    def __init__(self, root: Path, exists: bool) -> None:
        self.root, self.exists = root, exists

    def __truediv__(self, part: str) -> _Packaged:
        return _Packaged(self.root / part, self.exists)

    def is_file(self) -> bool:
        return self.exists

    def __str__(self) -> str:
        return str(self.root)


@pytest.fixture
def layout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Path]:
    paths = {"cwd": tmp_path / "cwd", "data": tmp_path / "data", "package": tmp_path / "pkg"}
    paths["cwd"].mkdir()
    monkeypatch.chdir(paths["cwd"])
    monkeypatch.setattr(validation.sysconfig, "get_path", lambda name: str(paths["data"]))
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    return paths


def _ancestors(name: str) -> list[Path]:
    return [parent / "schemas" / name for parent in Path(validation.__file__).resolve().parents]


def _data(layout: dict[str, Path], name: str) -> Path:
    return layout["data"] / "share" / "agentic-discipline" / "schemas" / name


def test_checkout_candidates_are_cwd_ancestors_then_installed_data(
    layout: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        validation.resources, "files", lambda package: _Packaged(layout["package"], False)
    )
    assert _schema_candidates("task.schema.json") == [
        layout["cwd"] / "schemas" / "task.schema.json",
        *_ancestors("task.schema.json"),
        _data(layout, "task.schema.json"),
    ]


def test_packaged_and_frozen_schemas_are_tried_first(
    layout: dict[str, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    requested: list[str] = []

    def files(package: str) -> _Packaged:
        requested.append(package)
        return _Packaged(layout["package"], True)

    monkeypatch.setattr(validation.resources, "files", files)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "frozen"), raising=False)

    assert _schema_candidates("x.json") == [
        layout["package"] / "schemas" / "x.json",
        tmp_path / "frozen" / "schemas" / "x.json",
        layout["cwd"] / "schemas" / "x.json",
        *_ancestors("x.json"),
        _data(layout, "x.json"),
    ]
    assert requested == ["agentic_discipline"]


@pytest.mark.parametrize("error", [ModuleNotFoundError("gone"), TypeError("namespace")])
def test_unavailable_package_resources_are_skipped(
    layout: dict[str, Path], monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def files(package: str) -> Any:
        raise error

    monkeypatch.setattr(validation.resources, "files", files)
    assert _schema_candidates("x.json")[0] == layout["cwd"] / "schemas" / "x.json"


def test_json_documents_must_exist_parse_and_be_objects(tmp_path: Path) -> None:
    good = tmp_path / "good.json"
    good.write_text('{"a": [1]}', encoding="utf-8")
    assert load_json(good) == {"a": [1]}

    missing = tmp_path / "missing.json"
    with pytest.raises(ValidationError) as caught:
        load_json(missing, "policy")
    assert str(caught.value) == f"policy not found: {missing}"

    broken = tmp_path / "broken.json"
    broken.write_text('{\n  "a": ,\n}', encoding="utf-8")
    with pytest.raises(json.JSONDecodeError) as decoded:
        json.loads(broken.read_text(encoding="utf-8"))
    with pytest.raises(ValidationError) as caught:
        load_json(broken)
    expected = decoded.value
    assert str(caught.value) == (
        f"JSON document is invalid JSON at line {expected.lineno}, "
        f"column {expected.colno}: {expected.msg}"
    )

    listed = tmp_path / "list.json"
    listed.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ValidationError) as caught:
        load_json(listed, "graph")
    assert str(caught.value) == "graph must be a JSON object"


def test_first_existing_schema_candidate_wins(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    first.write_text('{"title": "first"}', encoding="utf-8")
    second.write_text('{"title": "second"}', encoding="utf-8")
    (tmp_path / "directory.json").mkdir()
    candidates = [tmp_path / "missing.json", tmp_path / "directory.json", first, second]
    monkeypatch.setattr(validation, "_schema_candidates", lambda name: candidates)
    assert load_schema("anything") == {"title": "first"}


def test_missing_or_malformed_schemas_name_the_schema(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(validation, "_schema_candidates", lambda name: [tmp_path / "none.json"])
    with pytest.raises(ValidationError) as caught:
        load_schema("task.schema.json")
    assert str(caught.value) == "schema not found: task.schema.json"

    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    monkeypatch.setattr(validation, "_schema_candidates", lambda name: [broken])
    with pytest.raises(ValidationError) as caught:
        load_schema("task.schema.json")
    assert str(caught.value).startswith("schema task.schema.json is invalid JSON at line 1")


def test_schema_errors_are_sorted_by_path_with_dotted_locations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema = {
        "type": "object",
        "required": ["name"],
        "properties": {
            "items": {
                "type": "array",
                "items": {"type": "object", "properties": {"id": {"type": "string"}}},
            },
            "count": {"type": "integer"},
        },
    }
    requested: list[str] = []
    monkeypatch.setattr(validation, "load_schema", lambda name: requested.append(name) or schema)

    errors = validate_schema({"count": "many", "items": [{"id": 1}, {"id": "ok"}]}, "demo.json")

    assert requested == ["demo.json"]
    assert errors == [
        "$: 'name' is a required property",
        "count: 'many' is not of type 'integer'",
        "items.0.id: 1 is not of type 'string'",
    ]
    assert validate_schema({"name": "x"}, "demo.json") == []
