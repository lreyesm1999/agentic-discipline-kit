"""Canonical discipline loading, field by field.

Every agent surface (AGENTS.md, Cursor, Copilot, Claude skills) is compiled from the
disciplines loaded here. Existing tests checked a few defaults, so a frontmatter
quote could leak into a title, a glob list could keep blanks, a heading could render
twice, or a malformed file could load silently. Each case compares the whole value.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agentic_discipline.bootstrap import find_contract_root
from agentic_discipline.common import AgenticError
from agentic_discipline.skills import (
    Discipline,
    load_constitution,
    load_discipline,
    load_disciplines,
    parse_frontmatter,
    render_frontmatter,
)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _raises(message: str, action: Any, *args: Any) -> None:
    with pytest.raises(AgenticError) as caught:
        action(*args)
    assert str(caught.value) == message


def _discipline(**changes: Any) -> Discipline:
    fields: dict[str, Any] = {
        "id": "demo",
        "name": "demo",
        "title": "Demo",
        "description": "Keeps demos honest.",
        "when_to_use": "",
        "globs": ("**",),
        "always": False,
        "phase": "implementation",
        "body": "Body\n",
    }
    fields.update(changes)
    return Discipline(**fields)


# --- load_discipline ------------------------------------------------------------------------


def test_every_frontmatter_field_is_read(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "disciplines" / "demo-slug" / "SKILL.md",
        "---\n"
        "id: demo\n"
        "name: Demo name\n"
        "description: Keeps demos honest.\n"
        "when_to_use: When writing demos\n"
        "globs: src/** , tests/**, ,\n"
        "always: TRUE\n"
        "phase: review\n"
        "title: 'Demo: Title'\n"
        "---\n"
        "\n"
        "# Heading rendered by emitters\n"
        "First line\n"
        "\n"
        "Second line\n\n",
    )

    discipline = load_discipline(path)

    assert discipline == Discipline(
        id="demo",
        name="Demo name",
        title="Demo: Title",
        description="Keeps demos honest.",
        when_to_use="When writing demos",
        globs=("src/**", "tests/**"),
        always=True,
        phase="review",
        body="First line\n\nSecond line\n",
    )
    assert discipline.slug == "demo-slug"


def test_optional_fields_fall_back_to_defaults(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "plain" / "SKILL.md",
        "---\nid: plain-rule\nname: plain\ndescription: Plain.\n---\n#Not a heading\nText\n",
    )
    assert load_discipline(path) == Discipline(
        id="plain-rule",
        name="plain",
        title="Plain-Rule",
        description="Plain.",
        when_to_use="",
        globs=("**",),
        always=False,
        phase="implementation",
        body="#Not a heading\nText\n",
    )


@pytest.mark.parametrize(
    ("extra", "globs", "always"),
    [
        ("globs: ' , '\nalways: yes\n", ("**",), False),
        ("globs: docs/**\nalways: false\n", ("docs/**",), False),
        ("always: True\n", ("**",), True),
    ],
)
def test_glob_and_always_values(
    tmp_path: Path, extra: str, globs: tuple[str, ...], always: bool
) -> None:
    path = _write(
        tmp_path / "rule" / "SKILL.md",
        f"---\nid: rule\nname: rule\ndescription: Rule.\n{extra}---\n",
    )
    discipline = load_discipline(path)
    assert (discipline.globs, discipline.always, discipline.body) == (globs, always, "\n")


def test_missing_or_empty_required_keys_are_named_in_order(tmp_path: Path) -> None:
    path = _write(tmp_path / "broken" / "SKILL.md", "---\nid: broken\ndescription:\n---\nText\n")
    _raises(
        f"discipline {path} is missing frontmatter keys: name, description", load_discipline, path
    )


# --- parse_frontmatter and render_frontmatter -----------------------------------------------


def test_text_without_a_fence_is_all_body() -> None:
    assert parse_frontmatter("id: x\nbody\n", "file") == ({}, "id: x\nbody\n")
    assert parse_frontmatter("", "file") == ({}, "")


def test_frontmatter_values_are_split_on_the_first_colon_and_unquoted() -> None:
    text = (
        " --- \n"
        "url: http://example.invalid:8080\n"
        "\n"
        'double: "quoted"\n'
        "single: 'quoted'\n"
        "lone: '\n"
        "mixed: \"quoted'\n"
        "---\n"
        "\n\n"
        "  indented body\n"
    )
    assert parse_frontmatter(text, "file") == (
        {
            "url": "http://example.invalid:8080",
            "double": "quoted",
            "single": "quoted",
            "lone": "'",
            "mixed": "\"quoted'",
        },
        "  indented body",
    )


def test_malformed_frontmatter_is_refused_with_its_label() -> None:
    _raises(
        "invalid frontmatter line in a.md: 'no separator'",
        parse_frontmatter,
        "---\nno separator\n---\n",
        "a.md",
    )
    _raises("unterminated frontmatter in b.md", parse_frontmatter, "---\nid: x\n", "b.md")


@pytest.mark.parametrize("opener", ["*", "[", "{", "&", "!", "#"])
def test_rendered_values_are_quoted_only_when_yaml_needs_it(opener: str) -> None:
    fields = {"plain": "value", "special": f"{opener}value", "pair": "key: value", "number": 5}
    rendered = render_frontmatter(fields)
    assert rendered == (
        f"---\nplain: value\nspecial: '{opener}value'\npair: 'key: value'\nnumber: 5\n---\n"
    )
    assert parse_frontmatter(rendered + "body", "rendered") == (
        {"plain": "value", "special": f"{opener}value", "pair": "key: value", "number": "5"},
        "body",
    )


# --- Discipline properties ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("trigger", "summary"),
    [
        ("", "Keeps demos honest."),
        ("When writing demos", "Keeps demos honest. Use when writing demos"),
        ("Before merging", "Keeps demos honest. Use before merging"),
        ("After a failure", "Keeps demos honest. Use after a failure"),
        ("During review", "Keeps demos honest. Use during review"),
        ("Editing demo files", "Keeps demos honest. Use when: editing demo files"),
        ("Whenever", "Keeps demos honest. Use when: whenever"),
    ],
)
def test_summary_joins_description_and_trigger(trigger: str, summary: str) -> None:
    assert _discipline(when_to_use=trigger).summary == summary


def test_glob_list_joins_globs_or_matches_everything() -> None:
    assert _discipline(globs=("src/**", "tests/**")).glob_list == "src/**,tests/**"
    assert _discipline(globs=()).glob_list == "**"


def test_slug_does_not_affect_equality() -> None:
    assert _discipline(slug="one") == _discipline(slug="two")


# --- load_disciplines and load_constitution -------------------------------------------------


def test_disciplines_load_sorted_and_refuse_missing_empty_or_duplicate_sources(
    tmp_path: Path,
) -> None:
    kit = tmp_path / "kit"
    source = kit / "disciplines"
    _raises(f"canonical disciplines not found: {source}", load_disciplines, kit)
    source.mkdir(parents=True)
    _raises(f"no disciplines found under {source}", load_disciplines, kit)

    for slug, identifier in (("b-rule", "beta"), ("a-rule", "alpha")):
        _write(
            source / slug / "SKILL.md",
            f"---\nid: {identifier}\nname: {identifier}\ndescription: D.\n---\n",
        )
    assert [item.id for item in load_disciplines(kit)] == ["alpha", "beta"]

    for slug, identifier in (("c-rule", "beta"), ("d-rule", "alpha")):
        _write(
            source / slug / "SKILL.md",
            f"---\nid: {identifier}\nname: {identifier}\ndescription: D.\n---\n",
        )
    _raises("duplicate discipline ids: alpha, beta", load_disciplines, kit)


def test_the_kit_ships_loadable_disciplines() -> None:
    disciplines = load_disciplines(find_contract_root())
    assert disciplines
    assert len({item.id for item in disciplines}) == len(disciplines)


def test_constitution_is_read_with_one_trailing_newline(tmp_path: Path) -> None:
    path = tmp_path / "agentic" / "constitution" / "CORE.md"
    _raises(f"canonical constitution not found: {path}", load_constitution, tmp_path)
    _write(path, "Rule one\n\n\n")
    assert load_constitution(tmp_path) == "Rule one\n"


def test_empty_quoted_values_and_bodies_starting_with_quote_like_letters() -> None:
    assert parse_frontmatter("---\nempty: \"\"\nbare: ''\n---\nXylophone notes\n", "file") == (
        {"empty": "", "bare": ""},
        "Xylophone notes",
    )
