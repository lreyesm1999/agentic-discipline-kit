#!/usr/bin/env python3
"""A scoped, reproducible mutation campaign over the assurance engine.

`mutmut run` covers the whole package against the whole suite; in this environment it
either exhausts memory while generating that many mutants or deadlocks its workers, which
`docs/v2/VALIDATION.md` already records as a recurring hazard for this project. This
harness does the same job for one package: it rewrites a single syntax node, runs the
assurance test selection against the rewritten module, and asks whether the tests noticed.

It is deliberately narrow and deterministic. Mutants come from a fixed set of operator
families, the order is stable, and a survivor is reported with the exact line and the
before and after text, so the same run can be reproduced and a survivor can be triaged.

    python scripts/assurance_mutation.py --output docs/v2.1/evidence/mutation.json

Exit code 0 only when every mutant was killed.
"""

from __future__ import annotations

import argparse
import ast
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path("src/agentic_discipline")
TARGET = PACKAGE / "control" / "assurance"
# Every assurance test file, found rather than listed: a hand-written list once left a new
# test file out of a whole campaign, which then reported survivors that file kills.
SELECTION = sorted(
    p.relative_to(ROOT).as_posix() for p in (ROOT / "tests" / "control").glob("test_assurance_*.py")
)
# Everything a worker copy needs to run that selection. `find_contract_root` refuses a
# partial copy, so the contract bundle has to be here too.
COPIED = (
    "src",
    "tests",
    "pyproject.toml",
    "AGENTS.md",
    "MASTER_PROMPT.md",
    "schemas",
    "config",
    "policies",
    "disciplines",
    "skills",
    "agentic",
    "templates",
    "adapters",
    "examples",
)
COMPARISONS = {
    ast.Lt: ast.LtE,
    ast.LtE: ast.Lt,
    ast.Gt: ast.GtE,
    ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
}
SENTINEL = "XXmutatedXX"


class Mutation:
    """One rewritten node, identified by where it is rather than by a counter."""

    def __init__(self, module: str, line: int, family: str, before: str, after: str) -> None:
        self.module, self.line = module, line
        self.family, self.before, self.after = family, before, after

    @property
    def name(self) -> str:
        return f"{self.module}:{self.line}:{self.family}:{self.before}->{self.after}"

    def record(self) -> dict[str, Any]:
        return {
            "module": self.module,
            "line": self.line,
            "family": self.family,
            "before": self.before,
            "after": self.after,
        }


def docstrings(tree: ast.AST) -> set[int]:
    """Docstring constants carry no behaviour, so rewriting one proves nothing."""
    found: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", [])
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            if isinstance(body[0].value.value, str):
                found.add(id(body[0].value))
    return found


def returns_none(tree: ast.AST) -> set[int]:
    """A function annotated `-> None` cannot be mutated by replacing its return value."""
    found: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        annotation = node.returns
        if isinstance(annotation, ast.Constant) and annotation.value is None:
            for child in ast.walk(node):
                if isinstance(child, ast.Return):
                    found.add(id(child))
    return found


def candidates(tree: ast.AST) -> Iterator[tuple[ast.AST, str, str, str, Any]]:
    """Yield (node, family, before, after, replacement) for every mutable position."""
    skip_constants = docstrings(tree)
    skip_returns = returns_none(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for index, operator in enumerate(node.ops):
                swap = COMPARISONS.get(type(operator))
                if swap is None:
                    continue
                yield (
                    node,
                    "comparison",
                    type(operator).__name__,
                    swap.__name__,
                    ("ops", index, swap()),
                )
        elif isinstance(node, ast.BoolOp):
            swap = ast.Or if isinstance(node.op, ast.And) else ast.And
            yield (
                node,
                "boolean",
                type(node.op).__name__,
                swap.__name__,
                ("op", None, swap()),
            )
        elif isinstance(node, ast.If) and not isinstance(node.test, ast.UnaryOp):
            yield (node, "negation", "if cond", "if not cond", ("negate", None, None))
        elif isinstance(node, ast.Constant) and id(node) not in skip_constants:
            value = node.value
            if value is True or value is False:
                yield (
                    node,
                    "constant_bool",
                    repr(value),
                    repr(not value),
                    ("value", None, not value),
                )
            elif isinstance(value, int):
                yield (
                    node,
                    "constant_number",
                    repr(value),
                    repr(value + 1),
                    ("value", None, value + 1),
                )
            elif isinstance(value, str) and value and value != SENTINEL:
                yield (
                    node,
                    "constant_string",
                    "text",
                    SENTINEL,
                    ("value", None, SENTINEL),
                )
        elif (
            isinstance(node, ast.Return) and node.value is not None and id(node) not in skip_returns
        ):
            yield (node, "return_value", "return value", "return None", ("drop_return", None, None))
        elif isinstance(node, ast.Break):
            yield (node, "loop_control", "break", "continue", ("break", None, None))
        elif isinstance(node, ast.Continue):
            yield (node, "loop_control", "continue", "break", ("continue", None, None))


def apply(tree: ast.AST, position: int) -> tuple[str, Mutation] | None:
    """Rebuild the module with exactly the mutation at `position` applied."""
    clone = copy.deepcopy(tree)
    for index, (node, family, before, after, replacement) in enumerate(candidates(clone)):
        if index != position:
            continue
        field, slot, value = replacement
        # Which attribute exists is decided by the node's own kind, and `candidates` only
        # ever pairs a node with a field that kind has. Saying so in the type is honest;
        # silencing the checker line by line would not be.
        target: Any = node
        if field == "ops":
            target.ops[slot] = value
        elif field == "op":
            target.op = value
        elif field == "value":
            target.value = value
        elif field == "negate":
            target.test = ast.UnaryOp(op=ast.Not(), operand=target.test)
        elif field == "drop_return":
            target.value = None
        elif field == "break":
            return _swap_statement(clone, node, ast.Continue()), Mutation(
                "", getattr(node, "lineno", 0), family, before, after
            )
        elif field == "continue":
            return _swap_statement(clone, node, ast.Break()), Mutation(
                "", getattr(node, "lineno", 0), family, before, after
            )
        ast.fix_missing_locations(clone)
        return ast.unparse(clone), Mutation("", getattr(node, "lineno", 0), family, before, after)
    return None


def _swap_statement(tree: ast.AST, target: ast.AST, replacement: ast.stmt) -> str:
    for parent in ast.walk(tree):
        for _field, value in ast.iter_fields(parent):
            if not isinstance(value, list):
                continue
            for index, item in enumerate(value):
                if item is target:
                    value[index] = replacement
                    ast.fix_missing_locations(tree)
                    return ast.unparse(tree)
    raise AssertionError("statement to swap was not found in its own tree")


def plan(modules: list[Path]) -> list[tuple[Path, int, Mutation, str]]:
    work: list[tuple[Path, int, Mutation, str]] = []
    for module in modules:
        tree = ast.parse((ROOT / module).read_text(encoding="utf-8"))
        total = sum(1 for _ in candidates(copy.deepcopy(tree)))
        for position in range(total):
            applied = apply(tree, position)
            if applied is None:
                continue
            source, mutation = applied
            mutation.module = module.as_posix()
            work.append((module, position, mutation, source))
    return work


def worker_copy(base: Path, index: int) -> Path:
    destination = base / f"worker-{index}"
    destination.mkdir(parents=True)
    for name in COPIED:
        source = ROOT / name
        if source.is_dir():
            shutil.copytree(source, destination / name, symlinks=True)
        elif source.is_file():
            shutil.copy2(source, destination / name)
    return destination


def execute(workspace: Path, timeout: float) -> tuple[str, int, float]:
    environment = {
        **os.environ,
        "PYTHONPATH": str(workspace / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    started = time.monotonic()
    try:
        finished = subprocess.run(
            [sys.executable, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider", *SELECTION],
            cwd=workspace,
            env=environment,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "TIMEOUT", 124, round(time.monotonic() - started, 3)
    outcome = "KILLED" if finished.returncode != 0 else "SURVIVED"
    return outcome, finished.returncode, round(time.monotonic() - started, 3)


def key(record: dict[str, Any]) -> tuple[Any, ...]:
    return (record["module"], record["line"], record["family"], record["before"], record["after"])


def run(
    workers: int,
    timeout: float,
    limit: int | None,
    journal: Path | None = None,
    previous: dict[str, Any] | None = None,
    only: list[str] | None = None,
) -> dict[str, Any]:
    modules = sorted(p for p in (ROOT / TARGET).glob("*.py") if p.name != "__init__.py")
    relative = [p.relative_to(ROOT) for p in modules]
    work = plan(relative)
    total = len(work)
    if previous is not None:
        # Resuming is only sound over the identical mutant set: the same sources produce the
        # same mutants, and a suite that only gained tests can kill more but revive none.
        # Everything sharing a survivor's position is re-run, including mutants that were
        # killed there, so the carried-over kills are exactly those at other positions.
        per_module: dict[str, int] = {}
        for item in work:
            per_module[item[2].module] = per_module.get(item[2].module, 0) + 1
        same = previous.get("mutants") == total and (
            previous["sources"] == sources_digest(relative)
            if "sources" in previous
            # A report from before digests were recorded must at least agree mutant by
            # module; the digest is recorded from now on.
            else {m: v["mutants"] for m, v in previous["per_module"].items()} == per_module
        )
        if not same:
            raise SystemExit("the previous campaign did not run over these same sources")
        alive = {key(r) for r in previous["unresolved"]}
        work = [item for item in work if key(item[2].record()) in alive]
    if only:
        # A quick check of chosen positions; the report says it is partial.
        wanted = {tuple(item.rsplit(":", 1)) for item in only}
        work = [item for item in work if (Path(item[2].module).name, str(item[2].line)) in wanted]
    if limit:
        work = work[:limit]
    started = time.time()
    with tempfile.TemporaryDirectory(prefix="assurance-mutation-") as temporary:
        base = Path(temporary)
        copies = [worker_copy(base, index) for index in range(workers)]
        # The unmutated modules, rebuilt the same way a mutant is, must still pass. Without
        # this control a rewriting bug would look like a suite that kills everything.
        for module in relative:
            tree = ast.parse((ROOT / module).read_text(encoding="utf-8"))
            (copies[0] / module).write_text(ast.unparse(tree), encoding="utf-8")
        baseline, baseline_code, baseline_seconds = execute(copies[0], timeout)
        for module in relative:
            shutil.copy2(ROOT / module, copies[0] / module)
        if baseline != "SURVIVED":
            return {
                "status": "FAIL",
                "reason": "the rebuilt but unmutated modules do not pass the selection",
                "baseline_exit_code": baseline_code,
            }
        available: list[Path] = list(copies)
        results: list[dict[str, Any]] = []

        def evaluate(item: tuple[Path, int, Mutation, str]) -> dict[str, Any]:
            module, _, mutation, source = item
            workspace = available.pop()
            try:
                target = workspace / module
                original = target.read_bytes()
                target.write_text(source, encoding="utf-8")
                try:
                    outcome, code, seconds = execute(workspace, timeout)
                finally:
                    target.write_bytes(original)
            finally:
                available.append(workspace)
            return {**mutation.record(), "outcome": outcome, "exit_code": code, "seconds": seconds}

        # Each verdict is appended as it arrives, so an interrupted campaign keeps what it
        # already measured and its progress can be read while it runs.
        if journal is not None:
            journal.write_text("", encoding="utf-8")
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for done, result in enumerate(pool.map(evaluate, work), 1):
                results.append(result)
                if journal is not None:
                    with journal.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps({"done": done, "of": len(work), **result}) + "\n")
    counts = {
        outcome: sum(r["outcome"] == outcome for r in results)
        for outcome in ("KILLED", "SURVIVED", "TIMEOUT")
    }
    carried = 0
    if previous is not None:
        carried = total - len(work)
        counts["KILLED"] += carried
    unresolved = [r for r in results if r["outcome"] != "KILLED"]
    families = sorted({r["family"] for r in results})
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "harness": "scripts/assurance_mutation.py",
        "why_not_mutmut": "mutmut run over the whole package exhausts memory while generating"
        " mutants here, and a scoped run deadlocks its workers; this harness mutates one"
        " package and runs the assurance selection against each mutant",
        "scope": TARGET.as_posix(),
        "modules": [m.as_posix() for m in relative],
        "test_selection": SELECTION,
        "families": families,
        "baseline": {
            "outcome": baseline,
            "seconds": baseline_seconds,
            "meaning": "the modules rebuilt from their own syntax tree, unmutated, still pass",
        },
        "sources": sources_digest(relative),
        "method": "full campaign"
        if previous is None
        else "resumed: every position a previous campaign over the same sources left alive"
        " was re-run against the current suite; kills at other positions are carried over",
        "previous": None
        if previous is None
        else {
            "timestamp": previous["timestamp"],
            "counts": previous["counts"],
            "test_selection": previous["test_selection"],
        },
        "re_evaluated": len(results),
        "carried_over_kills": carried,
        "mutants": len(results) + carried,
        "counts": counts,
        "mutation_score": round(100 * counts["KILLED"] / (len(results) + carried), 2)
        if results or carried
        else 0.0,
        "per_module": {
            module: {
                "mutants": sum(r["module"] == module for r in results),
                "survived": sum(
                    r["module"] == module and r["outcome"] == "SURVIVED" for r in results
                ),
                "timed_out": sum(
                    r["module"] == module and r["outcome"] == "TIMEOUT" for r in results
                ),
            }
            for module in sorted({r["module"] for r in results})
        },
        "per_family": {
            family: {
                "mutants": sum(r["family"] == family for r in results),
                "survived": sum(
                    r["family"] == family and r["outcome"] == "SURVIVED" for r in results
                ),
            }
            for family in families
        },
        "unresolved": unresolved,
        "runtime_seconds": round(time.time() - started, 3),
        "partial": bool(only or limit),
        "status": "PASS" if not unresolved else "FAIL",
    }


def dispose(report: dict[str, Any], dispositions: dict[str, Any]) -> dict[str, Any]:
    """Subtract reviewed survivors, matched by the exact source of their line.

    Each disposition must match exactly as many survivors as it says. One that matches
    fewer is stale - its mutant was killed or its line changed - and fails the gate, so the
    list can only shrink by review. A timeout is never dispositioned.
    """
    modules = sorted(p for p in (ROOT / TARGET).glob("*.py") if p.name != "__init__.py")
    if report.get("sources") != sources_digest([p.relative_to(ROOT) for p in modules]):
        # Line numbers only mean something against the sources the campaign ran on.
        raise SystemExit("this report was produced from different sources; run it again")
    entries = dispositions["dispositions"]
    used = [0] * len(entries)
    remaining, accepted = [], []
    lines: dict[str, list[str]] = {}
    for survivor in report["unresolved"]:
        module = survivor["module"]
        lines.setdefault(module, (ROOT / module).read_text(encoding="utf-8").splitlines())
        source = lines[module][survivor["line"] - 1].strip()
        match = next(
            (
                i
                for i, e in enumerate(entries)
                if survivor["outcome"] == "SURVIVED"
                and e["module"] == Path(module).name
                and e["source"] == source
                and e["family"] == survivor["family"]
                and used[i] < e["count"]
            ),
            None,
        )
        if match is None:
            remaining.append(survivor)
        else:
            used[match] += 1
            accepted.append({**survivor, "kind": entries[match]["kind"]})
    stale = [
        {"module": e["module"], "source": e["source"], "expected": e["count"], "matched": n}
        for e, n in zip(entries, used, strict=True)
        if n != e["count"]
    ]
    kinds: dict[str, int] = {}
    for item in accepted:
        kinds[item["kind"]] = kinds.get(item["kind"], 0) + 1
    return {
        **report,
        "gate": {
            "dispositions": "docs/v2.1/evidence/mutation-dispositions.json",
            "accepted_survivors": len(accepted),
            "accepted_by_kind": kinds,
            "stale_dispositions": stale,
            "unresolved_after_review": len(remaining),
        },
        "accepted": accepted,
        "unresolved": remaining,
        "status": "PASS" if not remaining and not stale else "FAIL",
    }


def sources_digest(relative: list[Path]) -> str:
    import hashlib

    content = b"".join((ROOT / m).read_bytes() for m in sorted(relative))
    return hashlib.sha256(content).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--limit", type=int, help="evaluate only the first N mutants")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--journal", type=Path, help="append each verdict here as it arrives (JSON lines)"
    )
    parser.add_argument("--count", action="store_true", help="count the mutants and stop")
    parser.add_argument(
        "--dispositions",
        type=Path,
        help="reviewed survivor dispositions to subtract, matched by source text",
    )
    parser.add_argument(
        "--dispose",
        type=Path,
        help="apply --dispositions to this finished report instead of running a campaign",
    )
    parser.add_argument(
        "--only",
        nargs="*",
        help="evaluate only these module-file:line positions, e.g. service.py:190",
    )
    parser.add_argument(
        "--resume",
        type=Path,
        help="re-run only what this earlier report over the same sources left alive",
    )
    arguments = parser.parse_args()
    if arguments.count:
        modules = sorted(p for p in (ROOT / TARGET).glob("*.py") if p.name != "__init__.py")
        work = plan([p.relative_to(ROOT) for p in modules])
        summary: dict[str, int] = {}
        for _, _, mutation, _ in work:
            summary[mutation.family] = summary.get(mutation.family, 0) + 1
        print(json.dumps({"mutants": len(work), "per_family": summary}, indent=2))
        return 0
    if not 1 <= arguments.workers <= 16:
        parser.error("--workers must be 1..16")
    if arguments.dispose:
        if not arguments.dispositions:
            parser.error("--dispose needs --dispositions")
        report = dispose(
            json.loads(arguments.dispose.read_text(encoding="utf-8")),
            json.loads(arguments.dispositions.read_text(encoding="utf-8")),
        )
    else:
        previous = (
            json.loads(arguments.resume.read_text(encoding="utf-8")) if arguments.resume else None
        )
        report = run(
            arguments.workers,
            arguments.timeout,
            arguments.limit,
            arguments.journal,
            previous,
            arguments.only,
        )
        if arguments.dispositions and "unresolved" in report:
            report = dispose(report, json.loads(arguments.dispositions.read_text(encoding="utf-8")))
    output = json.dumps(report, indent=2) + "\n"
    if arguments.output:
        arguments.output.write_text(output, encoding="utf-8")
    print(output, end="")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
