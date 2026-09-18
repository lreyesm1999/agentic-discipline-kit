"""Both command-line surfaces compared with a reviewed snapshot.

Scripts, CI jobs and agents call these commands by name, option and default, so
the parser definition is a public contract. The snapshot records every
subcommand, argument, default, choice, requirement, help text and handler.
It is built from argparse's own structures rather than ``--help`` output, whose
layout changes between Python versions.

After an intentional CLI change, regenerate and review the snapshot with::

    python tests/test_cli_surface.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SNAPSHOT = Path(__file__).with_name("cli_surface.json")


def _value(value: Any) -> Any:
    if isinstance(value, Path):
        return "<cwd>" if value == Path.cwd() else value.as_posix()
    if isinstance(value, type) or callable(value):
        return getattr(value, "__name__", repr(value))
    if isinstance(value, (list, tuple)):
        return [_value(item) for item in value]
    return value


def _describe(parser: argparse.ArgumentParser) -> dict[str, Any]:
    arguments: list[dict[str, Any]] = []
    subcommands: dict[str, Any] | None = None
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            helps = {choice.dest: choice.help for choice in action._choices_actions}
            subcommands = {
                "dest": action.dest,
                "required": action.required,
                "commands": {
                    name: {"help": helps.get(name), **_describe(child)}
                    for name, child in action.choices.items()
                },
            }
            continue
        if isinstance(action, argparse._HelpAction):
            # argparse adds -h/--help itself; its wording is not part of this contract.
            continue
        arguments.append(
            {
                "action": type(action).__name__,
                "options": list(action.option_strings),
                "dest": action.dest,
                "nargs": action.nargs,
                "const": _value(action.const),
                "default": _value(action.default),
                "type": _value(action.type),
                "choices": _value(action.choices),
                "required": action.required,
                "help": action.help,
                "metavar": action.metavar,
                "version": getattr(action, "version", None),
            }
        )
    return {
        "description": parser.description,
        "defaults": {key: _value(value) for key, value in sorted(parser._defaults.items())},
        "arguments": arguments,
        "subcommands": subcommands,
    }


def _surface() -> dict[str, Any]:
    from agentic_discipline import cli
    from agentic_discipline.control import cli as control_cli

    parsers = {"agentic-discipline": cli.build_parser(), "agentic": control_cli.parser()}
    return {name: {"prog": parser.prog, **_describe(parser)} for name, parser in parsers.items()}


def test_cli_surfaces_match_the_reviewed_snapshot() -> None:
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert json.loads(json.dumps(_surface())) == expected


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    SNAPSHOT.write_text(json.dumps(_surface(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {SNAPSHOT}")
