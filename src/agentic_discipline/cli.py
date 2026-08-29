from __future__ import annotations

import argparse
import json
import shlex
import shutil
import sys
from pathlib import Path

from . import __version__
from .acceptance import compile_feature
from .bootstrap import bootstrap_project, initialize_project
from .common import AgenticError, changed_files, run_git
from .crap import crap_score
from .evidence import append_evidence, verify_ledger
from .integrity import audit_diff
from .quality import run_quality
from .requirements import orphan_requirements, validate_requirement_graph
from .risk import assess_risk, assess_risk_with_weights, level_at_least, load_risk_weights
from .validation import load_json, load_quality_config


def _json(data: object) -> None:
    print(json.dumps(data, indent=2, default=lambda value: value.__dict__))


def _doctor_root() -> Path:
    current = Path.cwd().resolve()
    candidates = [current, *current.parents]
    for candidate in candidates:
        if (
            (candidate / "AGENTS.md").is_file()
            and (candidate / "MASTER_PROMPT.md").is_file()
            and (candidate / "schemas" / "agentic-config.schema.json").is_file()
        ):
            return candidate
    return current


def command_doctor(args: argparse.Namespace) -> int:
    root = _doctor_root()
    git_available = shutil.which("git") is not None
    git_worktree = False
    if git_available:
        try:
            git_worktree = run_git(["rev-parse", "--is-inside-work-tree"], cwd=root).strip() == "true"
        except AgenticError:
            git_worktree = False
    skills_path = root / "skills"
    skill_count = len(list(skills_path.glob("*/SKILL.md"))) if skills_path.exists() else 0
    config_arg = getattr(args, "config", None)
    config_path = Path(config_arg) if config_arg else None
    if config_path is None:
        if (root / "agentic.config.json").is_file():
            config_path = root / "agentic.config.json"
        elif (root / "agentic.config.example.json").is_file():
            config_path = root / "agentic.config.example.json"
    config_valid = False
    tools: dict[str, bool] = {}
    config_error: str | None = None
    if config_path is not None:
        try:
            config = load_quality_config(config_path)
            config_valid = True
            if getattr(args, "check_tools", False):
                for gate in config["gates"]:
                    command = gate["command"]
                    executable = (
                        command[0] if isinstance(command, list) else shlex.split(command)[0]
                    )
                    tools[executable] = shutil.which(executable) is not None
        except AgenticError as exc:
            config_error = str(exc)
    required_files = {
        "agents_md": (root / "AGENTS.md").is_file(),
        "master_prompt": (root / "MASTER_PROMPT.md").is_file(),
        "config": config_path is not None and config_path.is_file(),
        "config_schema": (root / "schemas" / "agentic-config.schema.json").is_file(),
    }
    status = "PASS"
    if (
        not git_worktree
        or skill_count < 20
        or not all(required_files.values())
        or not config_valid
        or any(not available for available in tools.values())
    ):
        status = "FAIL"
    checks: dict[str, object] = {
        "python": sys.version.split()[0],
        "git": git_available,
        "git_worktree": git_worktree,
        "package_version": __version__,
        **required_files,
        "config_path": str(config_path) if config_path else None,
        "config_valid": config_valid,
        "config_error": config_error,
        "tools": tools,
        "skills": skill_count,
        "status": status,
    }
    _json(checks)
    return 0 if status == "PASS" else 1


def command_crap(args: argparse.Namespace) -> int:
    score = crap_score(args.complexity, args.coverage)
    result = {
        "complexity": args.complexity,
        "coverage": args.coverage,
        "crap": round(score, 4),
        "max": args.max,
        "status": "PASS" if score <= args.max else "FAIL",
    }
    _json(result)
    return 0 if result["status"] == "PASS" else 1


def command_acceptance(args: argparse.Namespace) -> int:
    result = compile_feature(Path(args.input), Path(args.output))
    _json(result)
    return 0


def command_graph(args: argparse.Namespace) -> int:
    graph_path = Path(args.graph)
    graph = load_json(graph_path, "requirement graph")
    issues = validate_requirement_graph(
        graph,
        base_path=graph_path.parent if getattr(args, "check_paths", False) else None,
        complete=getattr(args, "complete", False),
    )
    orphans = orphan_requirements(graph)
    status = "PASS" if not orphans and not issues else "FAIL"
    _json({"issues": issues, "orphans": orphans, "status": status})
    return 0 if status == "PASS" else 1


def command_risk(args: argparse.Namespace) -> int:
    try:
        files = changed_files(args.base_ref)
        diff = run_git(["diff", "--unified=0", args.base_ref, "--"])
    except AgenticError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    weights_path = getattr(args, "weights", None)
    if weights_path is None and Path("config/risk-weights.json").is_file():
        weights_path = "config/risk-weights.json"
    result = (
        assess_risk_with_weights(diff, files, load_risk_weights(Path(weights_path)))
        if weights_path
        else assess_risk(diff, files)
    )
    _json(result)
    fail_at = getattr(args, "fail_at", None)
    return 1 if fail_at and level_at_least(result.level, fail_at) else 0


def command_integrity(args: argparse.Namespace) -> int:
    try:
        diff = run_git(["diff", "--unified=0", args.base_ref, "--"])
    except AgenticError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    findings = audit_diff(diff)
    _json({"status": "FAIL" if findings else "PASS", "findings": findings})
    return 1 if findings else 0


def command_protected(args: argparse.Namespace) -> int:
    try:
        files = changed_files(args.base_ref)
    except AgenticError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    protected_prefixes = (
        "specs/",
        "acceptance/",
        "architecture/",
        "policies/",
        "schemas/",
        "skills/",
        ".github/workflows/",
    )
    protected_files = {"AGENTS.md", "MASTER_PROMPT.md", "agentic.config.json"}
    normalized = [path.replace("\\", "/") for path in files]
    changed = [
        path
        for path in normalized
        if path in protected_files or path.startswith(protected_prefixes)
    ]
    _json({"status": "FAIL" if changed else "PASS", "changed": changed})
    return 1 if changed else 0


def command_quality(args: argparse.Namespace) -> int:
    report = run_quality(Path(args.config))
    artifacts = Path(args.artifacts or report["artifacts_dir"])
    artifacts.mkdir(parents=True, exist_ok=True)
    output = artifacts / "quality-report.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    _json(report)
    return 0 if report["status"] == "PASS" else 1


def command_evidence(args: argparse.Namespace) -> int:
    record = append_evidence(
        Path(args.ledger),
        Path(args.artifact),
        tool=args.tool,
        command=args.executed_command,
        exit_code=args.exit_code,
    )
    _json(record)
    return 0 if args.exit_code == 0 else 1


def command_evidence_verify(args: argparse.Namespace) -> int:
    result = verify_ledger(Path(args.ledger), check_artifacts=args.check_artifacts)
    _json(result)
    return 0 if result["status"] == "PASS" else 1


def command_bootstrap(args: argparse.Namespace) -> int:
    actions = bootstrap_project(Path(args.target), getattr(args, "stack", None), args.force)
    _json({"status": "PASS", "actions": actions})
    return 0


def command_init(args: argparse.Namespace) -> int:
    result = initialize_project(
        Path(args.target),
        profile_ids=args.profile,
        profile_files=[Path(path) for path in args.profile_file],
        force=args.force,
        max_depth=args.max_depth,
    )
    _json(result)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentic-discipline")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("doctor", help="Validate repository installation")
    p.add_argument("--config")
    p.add_argument("--check-tools", action="store_true")
    p.set_defaults(func=command_doctor)

    p = sub.add_parser("crap", help="Calculate CRAP score")
    p.add_argument("--complexity", type=float, required=True)
    p.add_argument("--coverage", type=float, required=True)
    p.add_argument("--max", type=float, default=8.0)
    p.set_defaults(func=command_crap)

    p = sub.add_parser("compile-acceptance", help="Compile Gherkin-like acceptance into IR")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.set_defaults(func=command_acceptance)

    p = sub.add_parser("graph-check", help="Check requirement graph for orphan requirements")
    p.add_argument("--graph", required=True)
    p.add_argument("--check-paths", action="store_true")
    p.add_argument("--complete", action="store_true")
    p.set_defaults(func=command_graph)

    p = sub.add_parser("risk", help="Classify current git diff")
    p.add_argument("--base-ref", default="HEAD~1")
    p.add_argument("--weights")
    p.add_argument("--fail-at", choices=["LOW", "STANDARD", "HIGH", "CRITICAL"])
    p.set_defaults(func=command_risk)

    p = sub.add_parser("integrity", help="Scan current git diff for quality-gate bypasses")
    p.add_argument("--base-ref", default="HEAD~1")
    p.set_defaults(func=command_integrity)

    p = sub.add_parser("protected", help="Check protected contract paths")
    p.add_argument("--base-ref", default="HEAD~1")
    p.set_defaults(func=command_protected)

    p = sub.add_parser("quality", help="Run configured deterministic quality gates")
    p.add_argument("--config", default="agentic.config.json")
    p.add_argument("--artifacts")
    p.set_defaults(func=command_quality)

    p = sub.add_parser("evidence", help="Append an artifact hash to the evidence ledger")
    p.add_argument("--artifact", required=True)
    p.add_argument("--ledger", default="artifacts/evidence-ledger.jsonl")
    p.add_argument("--tool", required=True)
    p.add_argument("--executed-command", required=True)
    p.add_argument("--exit-code", type=int, required=True)
    p.set_defaults(func=command_evidence)

    p = sub.add_parser("evidence-verify", help="Verify the evidence hash chain")
    p.add_argument("--ledger", default="artifacts/evidence-ledger.jsonl")
    p.add_argument("--check-artifacts", action="store_true")
    p.set_defaults(func=command_evidence_verify)

    p = sub.add_parser(
        "init", help="Detect the project and install contracts plus quality configuration"
    )
    p.add_argument("--target", default=".")
    p.add_argument(
        "--profile",
        action="append",
        default=[],
        help="Override detection with a profile id; repeat for multi-stack projects",
    )
    p.add_argument(
        "--profile-file",
        action="append",
        default=[],
        help="Load an additional data-driven profile descriptor",
    )
    p.add_argument("--max-depth", type=int, default=4)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=command_init)

    p = sub.add_parser("bootstrap", help="Legacy alias for init")
    p.add_argument("--target", required=True)
    p.add_argument("--stack", help="Optional legacy profile override")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=command_bootstrap)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        code = args.func(args)
    except (AgenticError, OSError, ValueError) as exc:
        _json({"status": "ERROR", "error": str(exc)})
        code = 2
    raise SystemExit(code)


if __name__ == "__main__":
    main()
