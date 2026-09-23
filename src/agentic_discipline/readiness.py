"""Whether this project can actually run the workflow, and what to do when it cannot.

Installation health, project health and execution readiness are three different questions,
and answering them with one word is how a project ends up with every discipline installed,
no control plane, and a report that says PASS. Rules that nothing enforces are not the
product. So each check here names what is missing, whether it can be put right without a
human decision, and the command that does it.

Nothing in this module writes. `repair` acts on what these checks found.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .common import AgenticError

CONTROL_DIR = Path(".agentic") / "control"
STATE_DB = CONTROL_DIR / "state.db"
PAYLOAD_CONFIG = Path(".agentic") / "config.json"

# The disciplines a complete installation carries. A project with fewer has been installed
# by an older release or had its payload pruned.
EXPECTED_DISCIPLINES = 12

# What one check can say. PASS is proof; MISSING and STALE are repairable without a
# decision; FAIL needs a human; OFF is a choice the project recorded on purpose.
STATUSES = ("PASS", "MISSING", "STALE", "FAIL", "OFF")
REPAIRABLE = ("MISSING", "STALE")

# READY: the whole workflow is available. PARTIAL: every gap can be repaired safely.
# DEGRADED: the control plane is off by the project's own choice, so orchestration is
# unavailable and that is not a fault. BROKEN: something needs a human. NOT_INITIALIZED:
# the kit is not installed here at all.
STATES = ("READY", "PARTIAL", "DEGRADED", "BROKEN", "NOT_INITIALIZED")

INSTALLATION_CHECKS = (
    "installation",
    "version",
    "disciplines",
    "agent_adapter",
    "quality_gates",
)
PROJECT_CHECKS = ("control_plane", "project_adoption", "knowledge", "task_orchestration")
# Git is what both halves stand on: adoption records a baseline commit, and every
# verification binds to the tree git reports.
ENVIRONMENT_CHECKS = ("git_integration",)

LABELS = {
    "installation": "Installation",
    "version": "Version",
    "disciplines": "Disciplines",
    "agent_adapter": "Agent adapter",
    "quality_gates": "Quality gates",
    "control_plane": "Control plane",
    "project_adoption": "Project adoption",
    "knowledge": "Knowledge",
    "task_orchestration": "Task orchestration",
    "git_integration": "Git integration",
}


@dataclass(frozen=True)
class Check:
    """One observation, with the command that resolves it when a safe one exists."""

    name: str
    status: str
    detail: str
    repair: str | None = None
    # Drift, as opposed to a gap: the workflow is available and this catches up on its own
    # as work starts. An index a few edits behind is the normal state of an active
    # repository, and a check that turns red on every edit teaches people to ignore it.
    advisory: bool = False
    # The check this one is only failing because of. Three checks read the control plane, so
    # without it they report the same absence three more times; naming the cause lets a
    # reader, and a repair, treat them as one thing.
    caused_by: str | None = None

    @property
    def repairable(self) -> bool:
        return self.repair is not None and self.status in REPAIRABLE

    def report(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": LABELS[self.name],
            "status": self.status,
            "detail": self.detail,
            "repair": self.repair,
            "repairable": self.repairable,
            "advisory": self.advisory,
            "caused_by": self.caused_by,
        }


def control_mode(root: Path) -> str:
    """`managed` unless the project recorded that it wants the rules alone."""

    try:
        payload = json.loads((root / PAYLOAD_CONFIG).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "managed"
    mode = payload.get("control", {}).get("mode")
    return str(mode) if mode in {"managed", "rules-only"} else "managed"


# Two shapes of root answer to these checks. A project is a repository that installed the
# kit; a checkout is the kit's own source tree, which carries the contracts rather than a
# copy of them and never receives emitted adapters - `init` refuses to install the kit into
# itself. Both can be adopted by the control plane, so the project half applies to either.
SHAPES = ("project", "checkout", "absent")


def shape(root: Path) -> str:
    # Tested before the project shape, because adopting the kit's own checkout creates
    # `.agentic/control/` and would otherwise make the source tree look like a repository
    # that had installed a copy of itself.
    if (
        (root / "disciplines").is_dir()
        and (root / "AGENTS.md").is_file()
        and (root / "config" / "profiles").is_dir()
    ):
        return "checkout"
    if (root / ".agentic").is_dir() or (root / "agentic.config.json").is_file():
        return "project"
    return "absent"


def skill_count(root: Path) -> int:
    for relative in (Path(".agentic") / "skills", Path("disciplines")):
        directory = root / relative
        if directory.is_dir():
            return len(list(directory.glob("*/SKILL.md")))
    return 0


def _installation(root: Path, kind: str) -> Check:
    from . import __version__

    if kind == "checkout":
        return Check("installation", "PASS", f"kit checkout at version {__version__}")
    if kind == "absent":
        return Check(
            "installation",
            "MISSING",
            "Agentic Discipline is not installed in this directory",
            "agentic-discipline init",
        )
    missing = [
        name
        for name, present in (
            ("AGENTS.md", (root / "AGENTS.md").is_file()),
            (
                "MASTER_PROMPT.md",
                any(
                    (root / candidate).is_file()
                    for candidate in (
                        Path(".agentic") / "MASTER_PROMPT.md",
                        Path("MASTER_PROMPT.md"),
                    )
                ),
            ),
            (
                "schemas",
                any(
                    (root / candidate).is_dir()
                    for candidate in (Path(".agentic") / "schemas", Path("schemas"))
                ),
            ),
        )
        if not present
    ]
    if missing:
        return Check(
            "installation",
            "MISSING",
            f"the installation is incomplete: {', '.join(missing)}",
            "agentic-discipline init --force",
        )
    return Check("installation", "PASS", f"version {__version__}")


def _version(root: Path, kind: str) -> Check:
    """Whether this kit can manage this project's payload, in both directions."""

    from . import __version__
    from .bootstrap import PAYLOAD_SCHEMA
    from .migration import LEGACY_PATHS

    if kind != "project":
        return Check("version", "PASS", f"kit {__version__}")
    try:
        payload = json.loads((root / PAYLOAD_CONFIG).read_text(encoding="utf-8"))
        schema = str(payload["schema_version"])
    except (OSError, ValueError, KeyError):
        schema = ""
    installs = int(PAYLOAD_SCHEMA)
    carried = int(schema) if schema.isdigit() else installs
    if carried > installs:
        # Writing this release's layout over a newer one would silently downgrade the project.
        return Check(
            "version",
            "FAIL",
            f"the payload is schema {schema} and this kit installs {PAYLOAD_SCHEMA}:"
            " upgrade the kit rather than downgrading the project",
        )
    legacy = [path for path in LEGACY_PATHS if (root / path).exists()]
    if legacy:
        return Check(
            "version",
            "STALE",
            f"an earlier layout is still in the repository root: {', '.join(legacy)}."
            " The payload under .agentic/ is what is read; these are leftovers",
            "agentic-discipline migrate --prune",
            advisory=True,
        )
    if carried < installs:
        return Check(
            "version",
            "FAIL",
            f"the payload is schema {schema} and this kit installs {PAYLOAD_SCHEMA}:"
            " run `agentic-discipline migrate`, which rewrites generated files",
        )
    return Check("version", "PASS", f"kit {__version__}, payload schema {schema or PAYLOAD_SCHEMA}")


def _disciplines(root: Path) -> Check:
    count = skill_count(root)
    if count == 0:
        return Check(
            "disciplines", "MISSING", "no disciplines are installed", "agentic-discipline init"
        )
    if count < EXPECTED_DISCIPLINES:
        return Check(
            "disciplines",
            "STALE",
            f"{count} disciplines installed, {EXPECTED_DISCIPLINES} expected",
            "agentic-discipline init --force",
        )
    return Check("disciplines", "PASS", f"{count} installed")


def _agent_adapter(root: Path, kind: str) -> Check:
    """Staleness is measured the only way that cannot drift: by re-rendering them."""

    from .adapters import detect_adapters, sync_adapters

    if kind == "checkout":
        return Check("agent_adapter", "PASS", "the source tree holds the disciplines themselves")

    try:
        result = sync_adapters(root, detect_adapters(root), dry_run=True)
    except AgenticError as exc:
        return Check("agent_adapter", "FAIL", str(exc))
    actions = [str(action) for action in cast(list[object], result["actions"])]
    pending = [action for action in actions if not action.startswith("SKIP")]
    labels = ", ".join(str(label) for label in cast(list[object], result["labels"]))
    if pending:
        return Check(
            "agent_adapter",
            "STALE",
            f"{len(pending)} generated file(s) differ from the current disciplines",
            "agentic-discipline adapters sync",
        )
    return Check("agent_adapter", "PASS", labels)


def _quality_gates(root: Path, config: Path | None) -> Check:
    from .validation import load_quality_config

    # An explicitly named configuration is the one being asked about, wherever it lives.
    path = config or next(
        (
            root / name
            for name in ("agentic.config.json", "agentic.config.example.json")
            if (root / name).is_file()
        ),
        None,
    )
    if path is None:
        return Check(
            "quality_gates", "MISSING", "no quality configuration", "agentic-discipline init"
        )
    try:
        loaded = load_quality_config(path)
    except AgenticError as exc:
        return Check("quality_gates", "FAIL", str(exc))
    return Check("quality_gates", "PASS", f"{len(loaded['gates'])} gates in {path.name}")


def _control_plane(root: Path, kind: str, mode: str) -> tuple[Check, Any]:
    """Open the plane once, and say precisely which of the ways it can be absent this is."""

    from .control.store import Store

    directory = root / CONTROL_DIR
    database = root / STATE_DB
    if not database.exists():
        if directory.exists():
            # Never create a second database beside an unexplained one.
            return (
                Check(
                    "control_plane",
                    "FAIL",
                    f"{CONTROL_DIR.as_posix()} exists without a state database; inspect it"
                    " before adopting, since a second one would split the project's history",
                ),
                None,
            )
        if kind == "checkout":
            # The kit's own source tree is not a project under management. Adopting it is
            # how the kit is developed against itself, and it is a choice, not a repair.
            return (
                Check(
                    "control_plane",
                    "OFF",
                    "this is the kit's own source tree, which carries no adopted state until"
                    " someone adopts it on purpose",
                    "agentic adopt",
                ),
                None,
            )
        if mode == "rules-only":
            return (
                Check(
                    "control_plane",
                    "OFF",
                    "this project is installed rules-only, so orchestration is unavailable"
                    " on purpose",
                    "agentic-discipline init --adopt",
                ),
                None,
            )
        return (
            Check(
                "control_plane",
                "MISSING",
                "the control plane has never been initialised here",
                "agentic adopt",
            ),
            None,
        )
    try:
        store = Store(database)
    except (AgenticError, OSError, sqlite3.Error) as exc:
        return Check("control_plane", "FAIL", f"the state database cannot be opened: {exc}"), None
    version = str(store.schema_version)
    # A broken chain raises; an empty one returns UNKNOWN. Both mean the history cannot be
    # trusted, and neither is something an automatic repair may paper over.
    try:
        audit = store.audit()
    except AgenticError:
        store.close()
        return (
            Check(
                "control_plane",
                "FAIL",
                "the audit chain does not verify; the history has been altered",
            ),
            None,
        )
    except sqlite3.Error as exc:
        store.close()
        return Check("control_plane", "FAIL", f"the state database is unreadable: {exc}"), None
    if audit["status"] != "PASS":
        store.close()
        return Check("control_plane", "FAIL", "the audit chain holds no history"), None
    return Check("control_plane", "PASS", f"schema {version}, audit verified"), store


def _project_adoption(root: Path, store: Any) -> Check:
    if store is None:
        return Check(
            "project_adoption",
            "MISSING",
            "no project record, because there is no control plane",
            caused_by="control_plane",
        )
    records = store.list("project")
    if not records:
        return Check("project_adoption", "MISSING", "the control plane holds no project record")
    recorded = Path(str(records[0]["root"])).resolve()
    if recorded != root:
        return Check(
            "project_adoption",
            "FAIL",
            f"the control plane was adopted for {recorded}, not for this checkout",
        )
    return Check("project_adoption", "PASS", f"{records[0]['name']} at {recorded}")


def _knowledge(root: Path, store: Any, *, deep: bool) -> Check:
    if store is None:
        return Check(
            "knowledge",
            "MISSING",
            "no knowledge store, because there is no control plane",
            caused_by="control_plane",
        )
    files = [e for e in store.list("entity") if e["graph"] == "code" and not e.get("symbol_type")]
    if not files:
        return Check(
            "knowledge", "MISSING", "the project has never been indexed", "agentic reconcile"
        )
    if not deep:
        return Check("knowledge", "PASS", f"{len(files)} files indexed")
    from .control.discovery import scan

    try:
        fingerprint = scan(root)["fingerprint"]
    except (AgenticError, OSError) as exc:
        return Check("knowledge", "FAIL", f"the working tree cannot be scanned: {exc}")
    project = store.list("project")
    recorded = project[0].get("last_fingerprint") if project else None
    if recorded and recorded != fingerprint:
        return Check(
            "knowledge",
            "STALE",
            "the tree has changed since it was last indexed",
            "agentic reconcile",
            advisory=True,
        )
    return Check("knowledge", "PASS", f"{len(files)} files indexed")


def _task_orchestration(store: Any) -> Check:
    if store is None:
        return Check(
            "task_orchestration",
            "MISSING",
            "tasks, leases and checkpoints need the control plane",
            caused_by="control_plane",
        )
    if not store.list("policy"):
        return Check(
            "task_orchestration", "MISSING", "no execution policy is recorded", "agentic adopt"
        )
    tasks = store.list("task")
    active = sum(task["state"] not in {"COMPLETED", "CANCELLED"} for task in tasks)
    return Check("task_orchestration", "PASS", f"{len(tasks)} tasks, {active} open")


def _git_integration(root: Path) -> Check:
    from .control.discovery import git

    if shutil.which("git") is None:
        return Check("git_integration", "FAIL", "git is not installed")
    # `git` here reports failure as empty output, which is what a directory outside any
    # repository produces; that is a repairable state rather than a broken installation.
    if git(root, ["rev-parse", "--is-inside-work-tree"]) != "true":
        return Check(
            "git_integration",
            "MISSING",
            "this directory is not a git working tree, so no change can be bound to a commit",
            "git init",
            advisory=True,
        )
    return Check("git_integration", "PASS", "working tree")


def inspect(root: Path, *, deep: bool = True, config: Path | None = None) -> dict[str, Any]:
    """The whole picture, in the order a reader needs it."""

    root = root.resolve()
    mode = control_mode(root)
    kind = shape(root)
    checks = [
        _installation(root, kind),
        _version(root, kind),
        _disciplines(root),
        _agent_adapter(root, kind),
        _quality_gates(root, config),
    ]
    control, store = _control_plane(root, kind, mode)
    try:
        checks.extend(
            [
                control,
                _project_adoption(root, store),
                _knowledge(root, store, deep=deep),
                _task_orchestration(store),
            ]
        )
    finally:
        if store is not None:
            store.close()
    checks.append(_git_integration(root))
    return _verdict(root, kind, mode, checks)


def _verdict(root: Path, kind: str, mode: str, checks: list[Check]) -> dict[str, Any]:
    by_name = {check.name: check for check in checks}
    installation = _group(by_name, INSTALLATION_CHECKS)
    project = _group(by_name, PROJECT_CHECKS + ENVIRONMENT_CHECKS)
    failed = [check for check in checks if check.status == "FAIL"]
    repairable = [check for check in checks if check.repairable and not check.advisory]
    unrepairable = [
        check
        for check in checks
        if check.status in REPAIRABLE and not check.repairable and not check.advisory
    ]
    drift = [check for check in checks if check.advisory and check.status != "PASS"]
    if kind == "absent":
        state = "NOT_INITIALIZED"
        reason = "Agentic Discipline is not installed in this directory"
    elif failed:
        state = "BROKEN"
        reason = _first_reason(failed)
    elif by_name["control_plane"].status == "OFF":
        state = "DEGRADED"
        reason = by_name["control_plane"].detail
    elif repairable or unrepairable:
        state = "PARTIAL"
        reason = _first_reason([*repairable, *unrepairable])
    elif drift:
        state = "READY"
        reason = f"the full workflow is available; {_first_reason(drift)}"
    else:
        state = "READY"
        reason = "every check passes; the full workflow is available"
    return {
        "root": str(root),
        "shape": kind,
        "control_mode": mode,
        "installation": installation,
        "project": project,
        "execution_readiness": state,
        "reason": reason,
        "repairs": [check.repair for check in repairable],
        "drift": [check.name for check in drift],
        "checks": [check.report() for check in checks],
        "status": "PASS" if state == "READY" else "FAIL",
    }


def _group(by_name: dict[str, Check], names: tuple[str, ...]) -> str:
    statuses = {"PASS" if by_name[name].advisory else by_name[name].status for name in names}
    if "FAIL" in statuses:
        return "FAIL"
    return "PASS" if statuses <= {"PASS", "OFF"} else "PARTIAL"


def _first_reason(checks: list[Check]) -> str:
    check = checks[0]
    return f"{LABELS[check.name]}: {check.detail}"


def render(report: dict[str, Any]) -> str:
    """The table a person reads, with the same words the JSON uses."""

    summaries = ("Installation health", "Project health", "Execution readiness")
    width = max(
        *(len(str(check["label"])) for check in report["checks"]), *(len(s) for s in summaries)
    )
    lines = ["Agentic Discipline status", ""]
    lines += [f"{str(check['label']):<{width}}  {check['status']}" for check in report["checks"]]
    lines += [
        "",
        f"{summaries[0]:<{width}}  {report['installation']}",
        f"{summaries[1]:<{width}}  {report['project']}",
        f"{summaries[2]:<{width}}  {report['execution_readiness']}",
        "",
        f"Reason: {report['reason']}",
    ]
    outstanding = [check for check in report["checks"] if check["status"] != "PASS"]
    if outstanding:
        lines += ["", "Outstanding:"]
        lines += [
            f"- {check['label']} ({check['status']}): {check['detail']}"
            + (f"\n  Repair: {check['repair']}" if check["repair"] else "")
            for check in outstanding
        ]
    return "\n".join(lines)
