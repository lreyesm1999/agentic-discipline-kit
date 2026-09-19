#!/usr/bin/env python3
"""Fail release validation when mutmut's recorded survivors remain unresolved.

A survivor is resolved only by a test that kills it, or by a mechanical proof that
the mutation cannot change behaviour. The proof compares the original function with
the mutant in mutmut's `mutants/` tree: the two syntax trees must differ in exactly
one place, and that place must match one of these rules.

- `sql-case`: a string passed to `execute` changes only the letter case of SQL
  keywords or unquoted identifiers, which SQLite compares without regard to case.
  Quoted values and quoted identifiers must be unchanged.
- `codec-name`: an `encoding=` argument names the same codec in another case.
- `cast-type`: only the type argument of `typing.cast`, which is never evaluated
  against the value, changes.
- `ignorecase-pattern`: a pattern matched with `re.IGNORECASE` changes only the case
  of literal letters; escapes, group names and inline flags are unchanged.

A survivor no rule can prove may be accepted by a reviewed exception, read from the
file named by `--exceptions` (`policies/mutation-exceptions.json` in CI, a protected
path, so changing it needs review). An exception names the function and the exact
source line the mutant changes, before and after, so it keeps matching when mutmut
renumbers the mutants of that function. An exception that matches no survivor fails
the gate: the list cannot keep entries for mutants that were killed or removed.

Any other survivor stays unresolved, and the gate fails if the survivors it can read
do not match the count in mutmut's report.
"""

from __future__ import annotations

import argparse
import ast
import codecs
import difflib
import json
import re
from pathlib import Path
from typing import Any

REQUIRED = (
    "total",
    "killed",
    "survived",
    "timeout",
    "no_tests",
    "skipped",
    "suspicious",
    "check_was_interrupted_by_user",
    "segfault",
)
UNRESOLVED = REQUIRED[2:]

MUTANT = re.compile(r"^(?P<module>.+)\.(?P<function>[^.]+)__mutmut_(?P<number>\d+)$")
SQL_CALLS = {"execute", "executemany", "executescript"}
# Position of the `flags` argument for each `re` function.
REGEX_FLAGS = {
    "compile": 1,
    "search": 2,
    "match": 2,
    "fullmatch": 2,
    "findall": 2,
    "finditer": 2,
    "split": 3,
    "sub": 4,
    "subn": 4,
}

EXCEPTION_FIELDS = ("function", "original", "mutant", "family", "reason")

Ancestry = list[tuple[ast.AST, str, int | None]]
Difference = tuple[Ancestry, Any, Any]
Change = tuple[str, str, str]


def gate(
    report: Any,
    equivalent: dict[str, str] | None = None,
    reviewed: dict[str, str] | None = None,
    stale: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    if (
        not isinstance(report, dict)
        or set(report) != set(REQUIRED)
        or any(type(report.get(key)) is not int or report[key] < 0 for key in REQUIRED)
    ):
        return {"status": "FAIL", "reason": "Missing or invalid mutmut metrics"}
    # mutmut 3.8 omits not_checked and caught_by_type_check from its CI export.
    # Unaccounted variants fail closed until the report can explain them.
    if (
        report["total"] == 0
        or report["killed"] + sum(report[key] for key in UNRESOLVED) != report["total"]
    ):
        return {"status": "FAIL", "reason": "Incomplete or inconsistent mutation evidence"}
    proven = equivalent or {}
    accepted = reviewed or {}
    remaining = {key: report[key] for key in UNRESOLVED if report[key]}
    if proven or accepted:
        survived = report["survived"] - len(proven) - len(accepted)
        if survived:
            remaining["survived"] = survived
        else:
            remaining.pop("survived", None)
    result: dict[str, Any] = {
        "status": "FAIL" if remaining or stale else "PASS",
        "total": report["total"],
        "killed": report["killed"],
        "unresolved": remaining,
    }
    if proven:
        result["equivalent"] = {"total": len(proven), "by_rule": _tally(proven)}
        result["equivalent_mutants"] = {name: proven[name] for name in sorted(proven)}
    if accepted:
        result["reviewed"] = {"total": len(accepted), "by_family": _tally(accepted)}
        result["reviewed_mutants"] = {name: accepted[name] for name in sorted(accepted)}
    if stale:
        result["stale_exceptions"] = stale
    return result


def _tally(labels: dict[str, str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for label in labels.values():
        counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items()))


def load_exceptions(path: Path) -> list[dict[str, str]]:
    """Read the reviewed exceptions, refusing any entry that is incomplete or repeated."""

    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("exceptions") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise ValueError("exceptions file must hold an `exceptions` list")
    seen: set[Change] = set()
    for index, entry in enumerate(entries):
        if (
            not isinstance(entry, dict)
            or set(entry) != set(EXCEPTION_FIELDS)
            or not all(isinstance(entry[key], str) and entry[key].strip() for key in entry)
        ):
            raise ValueError(f"exception {index} needs exactly {', '.join(EXCEPTION_FIELDS)}")
        key = (entry["function"], entry["original"], entry["mutant"])
        if key in seen:
            raise ValueError(f"exception {index} repeats an earlier one")
        seen.add(key)
    return entries


def review(
    mutants: Path, names: list[str], exceptions: list[dict[str, str]]
) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Match survivors to exceptions by the line they change; return matches and stale entries."""

    families = {(e["function"], e["original"], e["mutant"]): e["family"] for e in exceptions}
    reviewed: dict[str, str] = {}
    used: set[Change] = set()
    trees: dict[Path, tuple[ast.Module, list[str]] | None] = {}
    for name in names:
        match = MUTANT.match(name)
        if not match:
            continue
        source = mutants / "src" / Path(*match["module"].split(".")).with_suffix(".py")
        if source not in trees:
            trees[source] = _parse_with_lines(source)
        parsed = trees[source]
        if parsed is None:
            continue
        change = _change(*parsed, match["function"], match["number"])
        if change is None:
            continue
        key = (f"{match['module']}.{match['function']}", *change)
        if key in families:
            reviewed[name] = families[key]
            used.add(key)
    stale = [e for e in exceptions if (e["function"], e["original"], e["mutant"]) not in used]
    return reviewed, stale


def _parse_with_lines(path: Path) -> tuple[ast.Module, list[str]] | None:
    try:
        text = path.read_text(encoding="utf-8")
        return ast.parse(text), text.splitlines()
    except (OSError, SyntaxError, ValueError):
        return None


def _change(
    module: ast.Module, lines: list[str], function: str, number: str
) -> tuple[str, str] | None:
    """The source lines the mutant removes and adds, each stripped and joined by newlines."""

    wanted = {f"{function}__mutmut_orig", f"{function}__mutmut_{number}"}
    found = {
        node.name: [line.strip() for line in lines[node.lineno : node.end_lineno]]
        for node in ast.walk(module)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in wanted
    }
    if len(found) != 2:
        return None
    delta = list(
        difflib.ndiff(found[f"{function}__mutmut_orig"], found[f"{function}__mutmut_{number}"])
    )
    removed = "\n".join(line[2:] for line in delta if line.startswith("- "))
    added = "\n".join(line[2:] for line in delta if line.startswith("+ "))
    if not removed and not added:
        return None
    return removed, added


def survivors(mutants: Path) -> list[str]:
    names: list[str] = []
    for meta in sorted(mutants.rglob("*.meta")):
        outcomes = json.loads(meta.read_text(encoding="utf-8")).get("exit_code_by_key", {})
        names.extend(name for name, code in outcomes.items() if code == 0)
    return sorted(names)


def prove_equivalent(mutants: Path, names: list[str]) -> dict[str, str]:
    trees: dict[Path, ast.Module | None] = {}
    proven: dict[str, str] = {}
    for name in names:
        match = MUTANT.match(name)
        if not match:
            continue
        source = mutants / "src" / Path(*match["module"].split(".")).with_suffix(".py")
        if source not in trees:
            trees[source] = _parse(source)
        module = trees[source]
        if module is None:
            continue
        rule = _rule(module, match["function"], match["number"])
        if rule:
            proven[name] = rule
    return proven


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return None


def _rule(module: ast.Module, function: str, number: str) -> str | None:
    wanted = {f"{function}__mutmut_orig", f"{function}__mutmut_{number}"}
    found = {
        node.name: node
        for node in ast.walk(module)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in wanted
    }
    if len(found) != 2:
        return None
    original, mutant = found[f"{function}__mutmut_orig"], found[f"{function}__mutmut_{number}"]
    differences: list[Difference] = []
    for field in ("args", "body", "decorator_list", "returns"):
        _compare(getattr(original, field), getattr(mutant, field), [], differences)
    if len(differences) != 1:
        return None
    ancestry, before, after = differences[0]
    for name, check in (
        ("codec-name", _codec_name),
        ("sql-case", _sql_case),
        ("cast-type", _cast_type),
        ("ignorecase-pattern", _ignorecase_pattern),
    ):
        if check(module, ancestry, before, after):
            return name
    return None


def _compare(before: Any, after: Any, ancestry: Ancestry, out: list[Difference]) -> None:
    """Record each place where two syntax trees differ, with the path that leads there."""

    if type(before) is not type(after):
        out.append((ancestry, before, after))
        return
    if isinstance(before, list):
        if len(before) != len(after):
            out.append((ancestry, before, after))
            return
        for index, (left, right) in enumerate(zip(before, after, strict=True)):
            located = (
                ancestry[:-1] + [(ancestry[-1][0], ancestry[-1][1], index)] if ancestry else []
            )
            _compare(left, right, located, out)
        return
    if isinstance(before, ast.Constant):
        if type(before.value) is not type(after.value) or before.value != after.value:
            out.append((ancestry, before, after))
        return
    if isinstance(before, ast.AST):
        for field in before._fields:
            if field != "ctx":
                _compare(
                    getattr(before, field, None),
                    getattr(after, field, None),
                    ancestry + [(before, field, None)],
                    out,
                )
        return
    if before != after:
        out.append((ancestry, before, after))


def _strings(before: Any, after: Any) -> tuple[str, str] | None:
    if (
        isinstance(before, ast.Constant)
        and isinstance(after, ast.Constant)
        and isinstance(before.value, str)
        and isinstance(after.value, str)
        and before.value != after.value
        and before.value.lower() == after.value.lower()
    ):
        return before.value, after.value
    return None


def _codec_name(module: ast.Module, ancestry: Ancestry, before: Any, after: Any) -> bool:
    values = _strings(before, after)
    if values is None or not ancestry:
        return False
    parent = ancestry[-1][0]
    if not isinstance(parent, ast.keyword) or parent.arg != "encoding":
        return False
    try:
        return codecs.lookup(values[0]).name == codecs.lookup(values[1]).name
    except LookupError:
        return False


def _sql_case(module: ast.Module, ancestry: Ancestry, before: Any, after: Any) -> bool:
    values = _strings(before, after)
    if values is None:
        return False
    for node, field, index in reversed(ancestry):
        if isinstance(node, (ast.JoinedStr, ast.BinOp)):
            continue
        if not (
            isinstance(node, ast.Call)
            and field == "args"
            and index == 0
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in SQL_CALLS
        ):
            return False
        return _outside_sql_quotes(*values)
    return False


def _outside_sql_quotes(before: str, after: str) -> bool:
    """Every changed character is an ASCII letter outside quotes; quotes are balanced."""

    if len(before) != len(after) or any(mark in before for mark in "`["):
        return False
    quote: str | None = None
    for left, right in zip(before, after, strict=True):
        if quote is None and left in "'\"":
            quote = left
        elif quote is not None and left == quote:
            quote = None
        if left != right and (quote is not None or not left.isascii() or not left.isalpha()):
            return False
    return quote is None


def _cast_type(module: ast.Module, ancestry: Ancestry, before: Any, after: Any) -> bool:
    imports_cast = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "typing"
        and any(alias.name == "cast" and alias.asname is None for alias in node.names)
        for node in module.body
    )
    if not imports_cast:
        return False
    return any(
        isinstance(node, ast.Call)
        and field == "args"
        and index == 0
        and isinstance(node.func, ast.Name)
        and node.func.id == "cast"
        for node, field, index in ancestry
    )


def _ignorecase_pattern(module: ast.Module, ancestry: Ancestry, before: Any, after: Any) -> bool:
    values = _strings(before, after)
    if values is None or not ancestry:
        return False
    call, field, index = ancestry[-1]
    if not (
        isinstance(call, ast.Call)
        and field == "args"
        and index == 0
        and isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "re"
        and call.func.attr in REGEX_FLAGS
    ):
        return False
    position = REGEX_FLAGS[call.func.attr]
    flags = [keyword.value for keyword in call.keywords if keyword.arg == "flags"]
    if len(call.args) > position:
        flags.append(call.args[position])
    if not any(_names_ignorecase(flag) for flag in flags):
        return False
    return _only_literal_case(*values)


def _names_ignorecase(node: ast.AST) -> bool:
    return any(
        isinstance(part, ast.Attribute)
        and isinstance(part.value, ast.Name)
        and part.value.id == "re"
        and part.attr in {"IGNORECASE", "I"}
        for part in ast.walk(node)
    )


def _only_literal_case(before: str, after: str) -> bool:
    """Escapes, `(?...)` constructs and named escapes are unchanged."""

    if len(before) != len(after) or "\\N{" in before:
        return False
    index = 0
    while index < len(before):
        if before[index] == "\\":
            if before[index : index + 2] != after[index : index + 2]:
                return False
            index += 2
            continue
        if before.startswith("(?", index):
            end = min(
                (
                    position
                    for position in (before.find(">", index), before.find(")", index))
                    if position != -1
                ),
                default=len(before) - 1,
            )
            if before[index : end + 1] != after[index : end + 1]:
                return False
            index = end + 1
            continue
        index += 1
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--mutants",
        type=Path,
        help="mutmut's mutants directory; defaults to the report's directory",
    )
    parser.add_argument(
        "--exceptions",
        type=Path,
        help="reviewed exceptions for survivors no rule proves; none unless given",
    )
    args = parser.parse_args()
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        mutants = args.mutants or args.report.parent
        exceptions = load_exceptions(args.exceptions) if args.exceptions else []
        equivalent: dict[str, str] | None = None
        reviewed: dict[str, str] | None = None
        stale: list[dict[str, str]] | None = None
        if (mutants / "src").is_dir():
            names = survivors(mutants)
            if isinstance(report, dict) and len(names) != report.get("survived"):
                result = {
                    "status": "FAIL",
                    "reason": f"Survivor evidence lists {len(names)} mutants, "
                    f"the report {report.get('survived')}",
                }
                print(json.dumps(result, sort_keys=True))
                return 1
            equivalent = prove_equivalent(mutants, names)
            if exceptions:
                unproven = [name for name in names if name not in equivalent]
                reviewed, stale = review(mutants, unproven, exceptions)
        elif exceptions:
            stale = exceptions
        result = gate(report, equivalent, reviewed, stale)
    except (OSError, ValueError) as exc:
        result = {"status": "FAIL", "reason": f"Cannot read mutation evidence: {exc}"}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
