from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import cast

from . import __version__, readiness, repair
from .acceptance import compile_feature
from .adapters import ADAPTERS, ALIASES, EMITTERS, LABELS, detect_adapters, sync_adapters
from .bootstrap import initialize_project
from .common import AgenticError, changed_files, run_git
from .crap import crap_score
from .evidence import append_evidence, verify_ledger
from .evolution import hygiene
from .integrity import IntegrityFinding, audit_changes
from .migration import migrate_payload
from .quality import run_quality
from .requirements import orphan_requirements, validate_requirement_graph
from .risk import assess_risk, assess_risk_with_weights, level_at_least, load_risk_weights
from .validation import load_json, load_quality_config
from .verifier.executor import execute_verifier
from .verifier.protection import check_protected_verifiers, protect_verifier
from .verifier.registry import list_verifiers, load_verifier, register_verifier
from .verifier.schema import load_and_validate_verifier, validate_verifier

EXPECTED_DISCIPLINES = readiness.EXPECTED_DISCIPLINES


def _json(data: object) -> None:
    print(json.dumps(data, indent=2, default=lambda value: value.__dict__))


def _doctor_root() -> Path:
    """Find the installed project or the kit checkout, whichever encloses cwd."""

    current = Path.cwd().resolve()
    for candidate in [current, *current.parents]:
        installed = (candidate / "AGENTS.md").is_file() and (candidate / ".agentic").is_dir()
        checkout = (candidate / "AGENTS.md").is_file() and (candidate / "disciplines").is_dir()
        if installed or checkout:
            return candidate
    return current


def _installed_skills(root: Path) -> int:
    return readiness.skill_count(root)


def _first_existing(root: Path, *candidates: Path) -> bool:
    return any((root / candidate).is_file() for candidate in candidates)


def _relative(path: str, root: Path) -> str:
    try:
        return Path(path).resolve().relative_to(root).as_posix()
    except ValueError:
        return path


def _counts(actions: list[str]) -> dict[str, int]:
    tally: dict[str, int] = {}
    for action in actions:
        verb = action.partition(" ")[0]
        tally[verb] = tally.get(verb, 0) + 1
    return tally


def _render_init(result: dict[str, object]) -> None:
    root = Path(str(result["target"])).resolve()
    dry_run = bool(result.get("dry_run"))
    detections = cast(list[dict[str, object]], result["detections"])
    adapters = cast(list[str], result["adapters"])
    labels = cast(list[str], result["adapter_labels"])
    relaxed = cast(list[dict[str, str]], result["relaxed_gates"])
    actions = [str(action) for action in cast(list[object], result["actions"])]

    print(f"Agentic Discipline -> {root}")
    print("DRY RUN - nothing was written." if dry_run else "")
    stacks = ", ".join(f"{item['label']} ({item['root']})" for item in detections)
    print(f"  Detected stack   {stacks}")
    print(f"  Disciplines      {len(cast(list[str], result['disciplines']))} installed")
    print(f"  Agent surfaces   {len(adapters)}")
    for label in labels:
        print(f"                   - {label}")
    print(f"  Quality gates    {result['gates']} generated, {len(relaxed)} relaxed")
    for gate in relaxed:
        reason = gate["note"].removeprefix("disabled by init: ")
        print(f"                   ! {gate['name']}: {reason}")
    baseline = result.get("baseline_gate")
    if baseline:
        print(f"                   + {baseline}: added so the config still checks something")
    tally = ", ".join(f"{count} {verb.lower()}" for verb, count in sorted(_counts(actions).items()))
    print(f"  Files            {tally}")
    control = cast(dict[str, object], result.get("control") or {})
    print(f"  Control plane    {str(control.get('detail', 'not attempted'))}")
    print("")
    print("Visible in your repository root: AGENTS.md, agentic.config.json")
    print("Everything else lives in .agentic/")
    print("")
    if relaxed:
        print("Review the relaxed gates in agentic.config.json before making CI blocking.")

    # What init claims is what the readiness checks measured after it finished writing, so
    # the closing line cannot say ready while the workflow is not.
    report = cast(dict[str, object] | None, result.get("readiness"))
    if report is None:
        print("Next:  agentic-discipline init        (this run wrote nothing)")
        return
    state = str(report["execution_readiness"])
    headline = {
        "READY": "Status: READY FOR AGENTIC EXECUTION",
        "DEGRADED": "Status: RULES ONLY - orchestration is not available",
    }.get(state, f"Status: {state}")
    print(headline)
    if state not in {"READY", "DEGRADED"}:
        print("")
        print(f"Reason: {report['reason']}")
        for check in cast(list[dict[str, object]], report["checks"]):
            if check["status"] == "PASS" or check["advisory"]:
                continue
            print(f"  - {check['label']} ({check['status']}): {check['detail']}")
            if check["repair"]:
                print(f"    Repair: {check['repair']}")
    print("")
    print(
        "Next:  ask for the work you want done."
        if state == "READY"
        else "Next:  agentic-discipline doctor --check-tools"
    )


def _render_adapters(result: dict[str, object], root: Path) -> None:
    actions = [str(action) for action in cast(list[object], result["actions"])]
    labels = cast(list[str], result["labels"])
    if result.get("dry_run"):
        print("DRY RUN - nothing was written.")
        print("")
    print(f"Compiled {len(cast(list[str], result['disciplines']))} disciplines for:")
    for label in labels:
        print(f"  - {label}")
    changed = [action for action in actions if not action.startswith("SKIP")]
    if not changed:
        print("")
        print("Everything already synchronized.")
        return
    print()
    for action in changed:
        verb, _, path = action.partition(" ")
        print(f"  {verb:<7}{_relative(path.split(' (')[0], root)}")


def command_doctor(args: argparse.Namespace) -> int:
    root = _doctor_root()
    git_available = shutil.which("git") is not None
    git_worktree = False
    if git_available:
        try:
            git_worktree = (
                run_git(["rev-parse", "--is-inside-work-tree"], cwd=root).strip() == "true"
            )
        except AgenticError:
            git_worktree = False
    skill_count = _installed_skills(root)
    config_arg = getattr(args, "config", None)
    config_path = Path(config_arg) if config_arg else None
    if config_path is None:
        if (root / "agentic.config.json").is_file():
            config_path = root / "agentic.config.json"
        elif (root / "agentic.config.example.json").is_file():
            config_path = root / "agentic.config.example.json"
    config_valid = False
    tools: dict[str, bool] = {}
    required_tool_missing = False
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
                    available = shutil.which(executable) is not None
                    tools[executable] = available
                    # A gate `init` already relaxed is reported but never fails
                    # the check, so a clean install does not open on red.
                    if not available and gate.get("required", True):
                        required_tool_missing = True
        except AgenticError as exc:
            config_error = str(exc)
    required_files = {
        "agents_md": (root / "AGENTS.md").is_file(),
        "master_prompt": _first_existing(
            root, Path(".agentic") / "MASTER_PROMPT.md", Path("MASTER_PROMPT.md")
        ),
        "config": config_path is not None and config_path.is_file(),
        "config_schema": _first_existing(
            root,
            Path(".agentic") / "schemas" / "agentic-config.schema.json",
            Path("schemas") / "agentic-config.schema.json",
        ),
    }
    # Installation facts alone once decided this, which is how a project with every
    # discipline installed and no control plane reported PASS. They are still reported,
    # because they are true and callers read them, but the verdict now comes from whether
    # the workflow can actually run.
    report = readiness.inspect(root, deep=not getattr(args, "fast", False), config=config_path)
    status = "PASS" if report["execution_readiness"] in {"READY", "DEGRADED"} else "FAIL"
    if (
        not git_worktree
        or skill_count < EXPECTED_DISCIPLINES
        or not all(required_files.values())
        or not config_valid
        or required_tool_missing
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
        "readiness": report,
        "status": status,
    }
    if getattr(args, "json", False):
        _json(checks)
    else:
        print(readiness.render(report))
    return 0 if status == "PASS" else 1


def command_repair(args: argparse.Namespace) -> int:
    result = repair.apply(
        _doctor_root(),
        dry_run=getattr(args, "dry_run", False),
        deep=not getattr(args, "fast", False),
    )
    if getattr(args, "json", False):
        _json(result)
    else:
        _render_repair(result)
    return 0 if result["status"] == "PASS" else 1


def _render_repair(result: dict[str, object]) -> None:
    report = cast(dict[str, object], result["readiness"])
    planned = cast(list[dict[str, object]], result["planned"])
    repaired = cast(list[dict[str, object]], result["repaired"])
    failed = cast(list[dict[str, object]], result["failed"])
    if result["dry_run"]:
        print("DRY RUN - nothing was written.")
    print(f"Execution readiness  {result['before']} -> {report['execution_readiness']}")
    print("")
    for entry in planned or repaired:
        print(f"  - {entry['action']}: {entry['outcome']}")
    for entry in failed:
        print(f"  ! {entry['action']}: {entry['outcome']}")
    if not planned and not repaired and not failed:
        print("  Nothing to repair.")
    # Only what no repair answers belongs under that heading: in a dry run the checks a
    # planned repair covers are not waiting on anybody.
    covered = {entry["check"] for entry in [*planned, *repaired, *failed]}
    remaining = [
        check
        for check in cast(list[dict[str, object]], report["checks"])
        if check["status"] != "PASS"
        and not check["advisory"]
        and check["name"] not in covered
        and check["caused_by"] not in covered
    ]
    # And a consequence of something already named above is not a second decision.
    named = {check["name"] for check in remaining}
    remaining = [check for check in remaining if check["caused_by"] not in named]
    if remaining:
        print("")
        print("Left for a person to decide:")
        for check in remaining:
            print(f"  - {check['label']} ({check['status']}): {check['detail']}")


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
    if weights_path is None:
        for candidate in (".agentic/config/risk-weights.json", "config/risk-weights.json"):
            if Path(candidate).is_file():
                weights_path = candidate
                break
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
    audit = audit_changes(diff, still_defined=_defined_in_repository)
    findings = list(audit.findings)
    findings.extend(
        IntegrityFinding(None, "protected_verifier", finding)
        for finding in check_protected_verifiers(Path.cwd())
    )
    _json(
        {
            "status": "FAIL" if findings else "PASS",
            "findings": findings,
            "retired_tests": audit.retired,
        }
    )
    return 1 if findings else 0


def _defined_in_repository(name: str) -> bool:
    """Whether any tracked file still defines ``name``; unknown counts as defined."""

    pattern = rf"(^|[^A-Za-z0-9_])(def|class|function)[[:space:]]+{name}([^A-Za-z0-9_]|$)"
    # Multi-threaded `git grep` intermittently crashes on some git builds (2.34 under WSL
    # segfaulted on 5 of 40 runs); a crash only makes the audit stricter, but a single
    # thread answers every time.
    process = subprocess.run(
        ["git", "grep", "--threads=1", "--quiet", "-E", pattern, "--", ":/"],
        capture_output=True,
    )
    return process.returncode != 1


def command_protected(args: argparse.Namespace) -> int:
    try:
        files = changed_files(args.base_ref)
    except AgenticError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    protected_prefixes = (
        ".agentic/",
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


def _adopt_choice(args: argparse.Namespace) -> bool | None:
    """None is the ordinary run: adopt unless the project recorded that it does not want to."""

    if getattr(args, "no_adopt", False):
        return False
    return True if getattr(args, "adopt", False) else None


def command_init(args: argparse.Namespace) -> int:
    result = initialize_project(
        Path(args.target),
        profile_ids=args.profile,
        profile_files=[Path(path) for path in args.profile_file],
        force=args.force,
        max_depth=args.max_depth,
        adapters=args.adapter or None,
        dry_run=args.dry_run,
        adopt=_adopt_choice(args),
        rules_only=getattr(args, "rules_only", False),
    )
    if args.json:
        _json(result)
    else:
        _render_init(result)
    # An install that did not reach a usable state says so in its exit code, so a script
    # that chains `init` with real work stops here instead of continuing half-configured.
    report = result.get("readiness")
    if isinstance(report, dict) and report["execution_readiness"] not in {"READY", "DEGRADED"}:
        return 1
    return 0


def command_verify(args: argparse.Namespace) -> int:
    root = Path(args.project_root).resolve()
    ids = (
        [args.verifier_id] if args.verifier_id else [entry["id"] for entry in list_verifiers(root)]
    )
    if not ids:
        _json({"status": "NOT_APPLICABLE", "results": []})
        return 0
    results = [execute_verifier(root, verifier_id) for verifier_id in ids]
    statuses = {result["status"] for result in results}
    status = "PASS" if statuses == {"PASS"} else ("BLOCKED" if "BLOCKED" in statuses else "FAIL")
    _json({"status": status, "results": results})
    return 0 if status == "PASS" else 1


def command_verifier_list(args: argparse.Namespace) -> int:
    _json({"status": "PASS", "verifiers": list_verifiers(Path(args.project_root))})
    return 0


def command_verifier_inspect(args: argparse.Namespace) -> int:
    metadata, directory = load_verifier(Path(args.project_root), args.verifier_id)
    _json({"status": "PASS", "directory": str(directory), "verifier": metadata})
    return 0


def command_verifier_validate(args: argparse.Namespace) -> int:
    if args.path:
        metadata = load_and_validate_verifier(Path(args.path))
    else:
        metadata, _directory = load_verifier(Path(args.project_root), args.verifier_id)
    errors = validate_verifier(metadata)
    _json({"status": "PASS" if not errors else "FAIL", "errors": errors, "verifier": metadata})
    return 0 if not errors else 1


def command_verifier_register(args: argparse.Namespace) -> int:
    entry = register_verifier(Path(args.path), Path(args.project_root))
    _json({"status": "PASS", "registered": entry})
    return 0


def command_verifier_protect(args: argparse.Namespace) -> int:
    entry = protect_verifier(Path(args.project_root), args.verifier_id)
    _json({"status": "PASS", "protected": entry})
    return 0


def command_adapters_sync(args: argparse.Namespace) -> int:
    root = Path(args.project_root).resolve()
    result = sync_adapters(root, args.adapter or None, dry_run=args.dry_run)
    if args.json:
        _json(result)
    else:
        _render_adapters(result, root)
    return 0


def command_adapters_list(args: argparse.Namespace) -> int:
    _json(
        {
            "status": "PASS",
            "adapters": [
                {"id": name, "label": LABELS[name], "output": ADAPTERS[name]}
                for name in sorted(EMITTERS)
            ],
            "aliases": ALIASES,
            "detected": detect_adapters(Path(args.project_root)),
        }
    )
    return 0


def command_migrate(args: argparse.Namespace) -> int:
    if args.to != "3.0":
        raise AgenticError("only migration target 3.0 is supported")
    result = migrate_payload(
        Path(args.project_root), force=args.force, prune=getattr(args, "prune", False)
    )
    _json(result)
    return 0


def command_hygiene(args: argparse.Namespace) -> int:
    result = hygiene(Path(args.project_root), args.base_ref)
    _json(result)
    return 0 if result["status"] == "PASS" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentic-discipline")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("doctor", help="Report installation, project and execution readiness")
    p.add_argument("--config")
    p.add_argument("--check-tools", action="store_true")
    p.add_argument(
        "--json", action="store_true", help="Emit the machine report instead of the table"
    )
    p.add_argument(
        "--fast",
        action="store_true",
        help="Skip the working-tree scan that detects stale project knowledge",
    )
    p.set_defaults(func=command_doctor)

    p = sub.add_parser(
        "repair", help="Repair what can be repaired without a decision, and report the rest"
    )
    p.add_argument(
        "--dry-run", action="store_true", help="Report what would be repaired without writing"
    )
    p.add_argument(
        "--fast", action="store_true", help="Skip the working-tree scan that detects drift"
    )
    p.add_argument("--json", action="store_true", help="Emit machine-readable output")
    p.set_defaults(func=command_repair)

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
    p.add_argument(
        "--adapter",
        action="append",
        default=[],
        help="Emit only these agent surfaces; repeat the option. Defaults to auto-detection",
    )
    p.add_argument(
        "--dry-run", action="store_true", help="Report what would change without writing"
    )
    p.add_argument(
        "--rules-only",
        action="store_true",
        help="Install the disciplines and quality configuration alone, recording that this"
        " project does not want the control plane",
    )
    p.add_argument(
        "--no-adopt",
        action="store_true",
        help="Skip the control plane for this run only, without recording a choice",
    )
    p.add_argument(
        "--adopt",
        action="store_true",
        help="Initialise the control plane even on a project previously installed rules-only",
    )
    p.add_argument("--json", action="store_true", help="Emit machine-readable output")
    p.set_defaults(func=command_init)

    p = sub.add_parser("verify", help="Execute registered deterministic verifiers")
    p.add_argument("verifier_id", nargs="?")
    p.add_argument("--project-root", default=".")
    p.set_defaults(func=command_verify)

    p = sub.add_parser("verifier", help="Manage verifier contracts and registry")
    verifier_sub = p.add_subparsers(dest="verifier_command", required=True)
    for name, function, help_text in (
        ("list", command_verifier_list, "List registered verifiers"),
        ("inspect", command_verifier_inspect, "Inspect a verifier contract"),
        ("validate", command_verifier_validate, "Validate verifier metadata"),
        ("register", command_verifier_register, "Register a verifier package"),
        ("protect", command_verifier_protect, "Protect a validated verifier"),
    ):
        child = verifier_sub.add_parser(name, help=help_text)
        child.set_defaults(func=function)
        child.add_argument("--project-root", default=".")
    verifier_sub.choices["inspect"].add_argument("verifier_id")
    verifier_sub.choices["validate"].add_argument("verifier_id", nargs="?")
    verifier_sub.choices["validate"].add_argument("--path")
    verifier_sub.choices["register"].add_argument("path")
    verifier_sub.choices["protect"].add_argument("verifier_id")

    p = sub.add_parser("adapters", help="Generate portable vendor adapters")
    adapters_sub = p.add_subparsers(dest="adapters_command", required=True)
    child = adapters_sub.add_parser("sync", help="Synchronize adapters idempotently")
    child.add_argument("--project-root", default=".")
    child.add_argument("--adapter", action="append", default=[])
    child.add_argument(
        "--dry-run", action="store_true", help="Report what would change without writing"
    )
    child.add_argument("--json", action="store_true", help="Emit machine-readable output")
    child.set_defaults(func=command_adapters_sync)

    child = adapters_sub.add_parser("list", help="List supported agent tools and their outputs")
    child.add_argument("--project-root", default=".")
    child.set_defaults(func=command_adapters_list)

    p = sub.add_parser("migrate", help="Migrate an earlier installation to the current payload")
    p.add_argument("--to", default="3.0")
    p.add_argument("--project-root", default=".")
    p.add_argument("--force", action="store_true")
    p.add_argument(
        "--prune",
        action="store_true",
        help="Delete the legacy root payload once it has been reinstalled under .agentic/",
    )
    p.set_defaults(func=command_migrate)

    p = sub.add_parser("hygiene", help="Check evolution lifecycle and repository hygiene")
    p.add_argument("--project-root", default=".")
    p.add_argument("--base-ref")
    p.set_defaults(func=command_hygiene)

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
