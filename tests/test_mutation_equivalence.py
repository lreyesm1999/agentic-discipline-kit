"""Mechanical equivalence proofs in the mutation gate, rule by rule.

The gate subtracts a survivor only when the original and the mutant differ in exactly
one place and that place matches a rule proven for every site of its shape. A rule
that accepted one real change would let a behaviour change through the gate, so each
rule is pinned by the mutations it must refuse as well as the ones it accepts.
"""

from __future__ import annotations

import json
import os
import runpy
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest

GATE_SCRIPT = next(
    parent / "scripts" / "mutation_gate.py"
    for parent in Path(__file__).resolve().parents
    if (parent / "scripts" / "mutation_gate.py").is_file()
)
GATE = runpy.run_path(str(GATE_SCRIPT))


def _clean_env(**extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "MUTATION_EXCEPTIONS"}
    return {**env, **extra}


MUTANT = "pkg.mod.x_target__mutmut_1"

HEADER = "import re\nfrom typing import cast\n\n"


def _mutants(tmp_path: Path, original: str, mutant: str, header: str = HEADER) -> Path:
    """A mutmut tree holding one function and one surviving mutant of it."""

    def function(name: str, body: str) -> str:
        return f"def {name}(db, path, value, line):\n" + textwrap.indent(
            textwrap.dedent(body).strip() + "\n", "    "
        )

    root = tmp_path / "mutants"
    module = root / "src" / "pkg" / "mod.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        header
        + function("x_target__mutmut_orig", original)
        + "\n"
        + function("x_target__mutmut_1", mutant),
        encoding="utf-8",
    )
    meta = {"exit_code_by_key": {MUTANT: 0}}
    (module.parent / "mod.py.meta").write_text(json.dumps(meta), encoding="utf-8")
    return root


def _rule(tmp_path: Path, original: str, mutant: str, header: str = HEADER) -> str | None:
    root = _mutants(tmp_path, original, mutant, header)
    return GATE["prove_equivalent"](root, [MUTANT]).get(MUTANT)


@pytest.mark.parametrize(
    ("original", "mutant", "rule"),
    [
        # SQL: keywords and unquoted identifiers may change case.
        (
            'db.execute("SELECT * FROM edges WHERE kind=?", (value,))',
            'db.execute("select * from edges where kind=?", (value,))',
            "sql-case",
        ),
        (
            "db.executemany(\"INSERT INTO edges VALUES (?, 'x')\", value)",
            "db.executemany(\"INSERT INTO EDGES VALUES (?, 'x')\", value)",
            "sql-case",
        ),
        (
            'db.execute(f"SELECT * FROM edges WHERE id={value}")',
            'db.execute(f"select * from edges where id={value}")',
            "sql-case",
        ),
        # Codec names resolve case-insensitively.
        (
            'path.write_text(value, encoding="utf-8")',
            'path.write_text(value, encoding="UTF-8")',
            "codec-name",
        ),
        ('path.read_text(encoding="latin-1")', 'path.read_text(encoding="LATIN-1")', "codec-name"),
        ('return value.encode("utf-8")', 'return value.encode("UTF-8")', "codec-name"),
        ('return value.decode("ascii")', 'return value.decode("ASCII")', "codec-name"),
        # cast never looks at its type argument.
        ("return cast(list[int], value)", "return cast(None, value)", "cast-type"),
        ("return cast(dict[str, int], value)", "return cast(dict[str, str], value)", "cast-type"),
        # Literal letters under re.IGNORECASE.
        (
            'return re.match(r"(Given|When)\\s+(.+)", line, re.IGNORECASE)',
            'return re.match(r"(GIVEN|WHEN)\\s+(.+)", line, re.IGNORECASE)',
            "ignorecase-pattern",
        ),
        (
            'return re.search(r"req:", line, flags=re.I)',
            'return re.search(r"REQ:", line, flags=re.I)',
            "ignorecase-pattern",
        ),
        (
            'return re.compile(r"when", re.IGNORECASE | re.MULTILINE)',
            'return re.compile(r"WHEN", re.IGNORECASE | re.MULTILINE)',
            "ignorecase-pattern",
        ),
        # Empty dict default in boolean condition.
        (
            'if dict.get("key", {}): return 1',
            'if dict.get("key", None): return 1',
            "dict-default-empty",
        ),
        (
            'if not dict.get("key", {}): return 1',
            'if not dict.get("key"): return 1',
            "dict-default-empty",
        ),
    ],
)
def test_each_rule_accepts_the_mutations_it_proves(
    tmp_path: Path, original: str, mutant: str, rule: str
) -> None:
    assert _rule(tmp_path, original, mutant) == rule


@pytest.mark.parametrize(
    ("original", "mutant"),
    [
        # A quoted SQL value is data: 'TASK' does not match 'task'.
        (
            "db.execute(\"SELECT * FROM r WHERE kind='TASK'\")",
            "db.execute(\"select * from r where kind='task'\")",
        ),
        # A double-quoted name may be read as a string literal by SQLite.
        ("db.execute('SELECT \"Name\" FROM r')", "db.execute('SELECT \"NAME\" FROM r')"),
        # Bracket and backtick quoting are not parsed, so they are refused.
        ("db.execute('SELECT [Name] FROM r')", "db.execute('SELECT [NAME] FROM r')"),
        # SQL case only matters where the string reaches execute.
        ('value = "SELECT * FROM r"', 'value = "select * from r"'),
        ('db.execute("SELECT 1", "Mode")', 'db.execute("SELECT 1", "MODE")'),
        # A changed letter that is not ASCII is not folded by SQLite.
        ('db.execute("SELECT * FROM é")', 'db.execute("SELECT * FROM É")'),
        # Only the encoding argument names a codec.
        ('path.write_text(value, errors="Strict")', 'path.write_text(value, errors="strict")'),
        (
            'path.write_text(value, encoding="utf-8")',
            'path.write_text(value, encoding="XXutf-8XX")',
        ),
        # Positionally, only the first argument of encode or decode names a codec.
        ('return value.encode("utf-8", "Strict")', 'return value.encode("utf-8", "strict")'),
        ('return value.replace("utf-8")', 'return value.replace("UTF-8")'),
        # cast's value argument is behaviour.
        ("return cast(list[int], value)", "return cast(list[int], None)"),
        # Without re.IGNORECASE, case is behaviour.
        ('return re.match(r"Given", line)', 'return re.match(r"GIVEN", line)'),
        (
            'return re.match(r"Given", line, re.MULTILINE)',
            'return re.match(r"GIVEN", line, re.MULTILINE)',
        ),
        # An escape changes meaning with its case: \s is whitespace, \S is not.
        ('return re.match(r"a\\s", line, re.I)', 'return re.match(r"a\\S", line, re.I)'),
        # A group name is looked up by case.
        (
            'return re.match(r"(?P<Name>x)", line, re.I)',
            'return re.match(r"(?P<NAME>x)", line, re.I)',
        ),
        # For re.split the third positional argument is maxsplit, not flags.
        ('return re.split(r"a", line, re.I)', 'return re.split(r"A", line, re.I)'),
        # A second difference anywhere makes the whole mutant unproven.
        (
            'db.execute("SELECT 1")\nreturn value + 1',
            'db.execute("select 1")\nreturn value + 2',
        ),
        # True and 1 compare equal but are different constants, so this is a second
        # difference, not none.
        (
            'db.execute("SELECT 1")\nreturn render(value, flag=True)',
            'db.execute("select 1")\nreturn render(value, flag=1)',
        ),
        # Only cast ignores its first argument.
        ("return convert(list[int], value)", "return convert(None, value)"),
        # With no difference at all there is nothing to prove.
        ('db.execute("SELECT 1")', 'db.execute("SELECT 1")'),
        # A codec name outside `encoding=` is just a string.
        ('return render(value, name="utf-8")', 'return render(value, name="UTF-8")'),
        # A name that is no codec proves nothing.
        ('path.write_text(value, encoding="Foo")', 'path.write_text(value, encoding="FOO")'),
        # A quote opened in one f-string fragment and closed in the next: the tail is
        # inside a SQL literal although this fragment shows no opening quote.
        (
            "db.execute(f\"SELECT * FROM r WHERE a='{value} Tail'\")",
            "db.execute(f\"SELECT * FROM r WHERE a='{value} TAIL'\")",
        ),
    ],
)
def test_each_rule_refuses_mutations_that_can_change_behaviour(
    tmp_path: Path, original: str, mutant: str
) -> None:
    assert _rule(tmp_path, original, mutant) is None


def test_cast_must_be_typing_cast(tmp_path: Path) -> None:
    header = "import re\n\n\ndef cast(kind, value):\n    return kind(value)\n\n"
    assert _rule(tmp_path, "return cast(int, value)", "return cast(None, value)", header) is None


def test_an_unreadable_or_missing_mutant_is_not_proven(tmp_path: Path) -> None:
    root = _mutants(tmp_path, 'db.execute("SELECT 1")', 'db.execute("select 1")')
    prove = GATE["prove_equivalent"]

    assert prove(root, ["pkg.mod.x_target__mutmut_2"]) == {}
    assert prove(root, ["pkg.other.x_target__mutmut_1"]) == {}
    assert prove(root, ["not a mutant name"]) == {}
    (root / "src" / "pkg" / "mod.py").write_text("def broken(:\n", encoding="utf-8")
    assert GATE["prove_equivalent"](root, [MUTANT]) == {}


def test_survivors_are_read_from_every_meta_file(tmp_path: Path) -> None:
    root = tmp_path / "mutants"
    (root / "src" / "a").mkdir(parents=True)
    (root / "src" / "a" / "x.py.meta").write_text(
        json.dumps({"exit_code_by_key": {"a.x.f__mutmut_1": 0, "a.x.f__mutmut_2": 1}}),
        encoding="utf-8",
    )
    (root / "src" / "b.py.meta").write_text(
        json.dumps({"exit_code_by_key": {"b.g__mutmut_3": 0, "b.g__mutmut_4": None}}),
        encoding="utf-8",
    )

    assert GATE["survivors"](root) == ["a.x.f__mutmut_1", "b.g__mutmut_3"]


def _report(**changes: int) -> dict[str, int]:
    report = {
        "total": 10,
        "killed": 8,
        "survived": 2,
        "timeout": 0,
        "no_tests": 0,
        "skipped": 0,
        "suspicious": 0,
        "check_was_interrupted_by_user": 0,
        "segfault": 0,
    }
    report.update(changes)
    return report


def test_proven_survivors_are_subtracted_and_listed() -> None:
    result = GATE["gate"](_report(), {"m.f__mutmut_1": "sql-case"})

    assert result == {
        "status": "FAIL",
        "total": 10,
        "killed": 8,
        "unresolved": {"survived": 1},
        "equivalent": {"total": 1, "by_rule": {"sql-case": 1}},
        "equivalent_mutants": {"m.f__mutmut_1": "sql-case"},
    }


def test_the_gate_passes_only_when_every_survivor_is_proven_and_nothing_else_remains() -> None:
    proven = {"m.f__mutmut_1": "sql-case", "m.f__mutmut_2": "cast-type"}

    assert GATE["gate"](_report(), proven)["status"] == "PASS"
    assert GATE["gate"](_report(), proven)["unresolved"] == {}
    timed_out = GATE["gate"](_report(killed=7, timeout=1), proven)
    assert timed_out["status"] == "FAIL"
    assert timed_out["unresolved"] == {"timeout": 1}


def _run(tmp_path: Path, report: dict[str, Any], mutants: Path | None) -> tuple[int, Any]:
    path = (mutants or tmp_path) / "mutmut-cicd-stats.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report), encoding="utf-8")
    process = subprocess.run(
        [sys.executable, str(GATE_SCRIPT), "--report", str(path)],
        capture_output=True,
        text=True,
        env=_clean_env(),
    )
    return process.returncode, json.loads(process.stdout)


def test_the_command_reads_the_mutants_beside_the_report(tmp_path: Path) -> None:
    root = _mutants(tmp_path, 'db.execute("SELECT 1")', 'db.execute("select 1")')

    code, result = _run(tmp_path, _report(killed=9, survived=1), root)

    assert code == 0
    assert result["status"] == "PASS"
    assert result["equivalent_mutants"] == {MUTANT: "sql-case"}


def test_the_command_fails_when_the_survivors_do_not_match_the_report(tmp_path: Path) -> None:
    root = _mutants(tmp_path, 'db.execute("SELECT 1")', 'db.execute("select 1")')

    code, result = _run(tmp_path, _report(), root)

    assert code == 1
    assert result == {
        "status": "FAIL",
        "reason": "Survivor evidence lists 1 mutants, the report 2",
    }


def test_without_a_mutants_tree_every_survivor_stays_unresolved(tmp_path: Path) -> None:
    code, result = _run(tmp_path, _report(), None)

    assert code == 1
    assert result["unresolved"] == {"survived": 2}
    assert "equivalent" not in result


# --- reviewed exceptions --------------------------------------------------------------------


def _exception(**changes: str) -> dict[str, str]:
    entry = {
        "function": "pkg.mod.x_target",
        "original": 'return value.get("flag", False)',
        "mutant": 'return value.get("flag", None)',
        "family": "falsy-default",
        "reason": "only tested for truth",
    }
    entry.update(changes)
    return entry


def _flag_tree(tmp_path: Path) -> Path:
    return _mutants(tmp_path, 'return value.get("flag", False)', 'return value.get("flag", None)')


def test_an_exception_matches_the_survivor_by_the_line_it_changes(tmp_path: Path) -> None:
    root = _flag_tree(tmp_path)

    reviewed, stale = GATE["review"](root, [MUTANT], [_exception()])

    assert (reviewed, stale) == ({MUTANT: "falsy-default"}, [])


def test_an_exception_for_another_change_or_function_matches_nothing(tmp_path: Path) -> None:
    root = _flag_tree(tmp_path)
    other_line = _exception(mutant='return value.get("flag", 0)')
    other_function = _exception(function="pkg.mod.x_other")

    reviewed, stale = GATE["review"](root, [MUTANT], [other_line, other_function])

    assert (reviewed, stale) == ({}, [other_line, other_function])


def test_reviewed_survivors_are_subtracted_and_listed_apart_from_proofs() -> None:
    result = GATE["gate"](
        _report(), {"m.f__mutmut_1": "sql-case"}, {"m.g__mutmut_4": "falsy-default"}
    )

    assert result["status"] == "PASS"
    assert result["unresolved"] == {}
    assert result["reviewed"] == {"total": 1, "by_family": {"falsy-default": 1}}
    assert result["reviewed_mutants"] == {"m.g__mutmut_4": "falsy-default"}


def test_a_stale_exception_fails_the_gate_even_when_nothing_else_remains() -> None:
    stale = [_exception()]

    result = GATE["gate"](_report(killed=10, survived=0), None, None, stale)

    assert result["status"] == "FAIL"
    assert result["stale_exceptions"] == stale


@pytest.mark.parametrize(
    "data",
    [
        [],
        {"exceptions": {}},
        {"exceptions": [{**_exception(), "extra": "x"}]},
        {"exceptions": [{k: v for k, v in _exception().items() if k != "reason"}]},
        {"exceptions": [_exception(reason="  ")]},
        {"exceptions": [_exception(original="", mutant=" ")]},
        {"exceptions": [_exception(), _exception(reason="said again")]},
    ],
    ids=[
        "not-an-object",
        "not-a-list",
        "extra-field",
        "missing-field",
        "blank",
        "no-change",
        "repeated",
    ],
)
def test_an_incomplete_or_repeated_exception_file_is_refused(tmp_path: Path, data: Any) -> None:
    path = tmp_path / "exceptions.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError):
        GATE["load_exceptions"](path)


def _run_with(tmp_path: Path, report: dict[str, Any], root: Path, entries: Any) -> tuple[int, Any]:
    exceptions = tmp_path / "exceptions.json"
    exceptions.write_text(json.dumps({"exceptions": entries}), encoding="utf-8")
    path = root / "mutmut-cicd-stats.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    process = subprocess.run(
        [sys.executable, str(GATE_SCRIPT), "--report", str(path), "--exceptions", str(exceptions)],
        capture_output=True,
        text=True,
        env=_clean_env(),
    )
    return process.returncode, json.loads(process.stdout)


def test_the_command_accepts_a_survivor_its_exceptions_name(tmp_path: Path) -> None:
    root = _flag_tree(tmp_path)

    code, result = _run_with(tmp_path, _report(killed=9, survived=1), root, [_exception()])

    assert (code, result["status"]) == (0, "PASS")
    assert result["reviewed_mutants"] == {MUTANT: "falsy-default"}


def test_the_command_fails_on_an_exception_no_survivor_needs(tmp_path: Path) -> None:
    root = _flag_tree(tmp_path)
    unused = _exception(function="pkg.mod.x_gone")

    code, result = _run_with(tmp_path, _report(killed=9, survived=1), root, [_exception(), unused])

    assert (code, result["status"]) == (1, "FAIL")
    assert result["stale_exceptions"] == [unused]


def test_the_command_refuses_an_invalid_exceptions_file(tmp_path: Path) -> None:
    root = _flag_tree(tmp_path)

    code, result = _run_with(tmp_path, _report(killed=9, survived=1), root, [{"function": "x"}])

    assert code == 1
    assert result["reason"].startswith("Cannot read mutation evidence: exception 0 needs")


def test_an_exception_can_name_a_changed_parameter_default(tmp_path: Path) -> None:
    root = tmp_path / "mutants"
    module = root / "src" / "pkg" / "mod.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        "def x_target__mutmut_orig(port: int = 8765):\n    return port\n\n"
        "def x_target__mutmut_1(port: int = 8766):\n    return port\n",
        encoding="utf-8",
    )
    entry = _exception(
        original="def x_target(port: int = 8765):", mutant="def x_target(port: int = 8766):"
    )

    assert GATE["review"](root, [MUTANT], [entry]) == ({MUTANT: "falsy-default"}, [])


def test_an_exception_may_name_a_deleted_line(tmp_path: Path) -> None:
    path = tmp_path / "exceptions.json"
    entry = _exception(original="check=False,", mutant="")
    path.write_text(json.dumps({"exceptions": [entry]}), encoding="utf-8")

    assert GATE["load_exceptions"](path) == [entry]


def test_the_command_reads_the_exception_file_named_by_the_environment(tmp_path: Path) -> None:
    root = _flag_tree(tmp_path)
    exceptions = tmp_path / "exceptions.json"
    exceptions.write_text(json.dumps({"exceptions": [_exception()]}), encoding="utf-8")
    report = root / "mutmut-cicd-stats.json"
    report.write_text(json.dumps(_report(killed=9, survived=1)), encoding="utf-8")

    process = subprocess.run(
        [sys.executable, str(GATE_SCRIPT), "--report", str(report)],
        capture_output=True,
        text=True,
        env=_clean_env(MUTATION_EXCEPTIONS=str(exceptions)),
    )

    assert process.returncode == 0
    assert json.loads(process.stdout)["reviewed_mutants"] == {MUTANT: "falsy-default"}
