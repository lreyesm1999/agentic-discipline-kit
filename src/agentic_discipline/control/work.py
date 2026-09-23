"""From a request in someone's own words to a task the control plane governs.

The user should not have to write a task contract, so this derives one - and derives it only
from things that are already recorded: the request itself, the project's requirements, its
knowledge graph, its quality gates, its risk rules and its policy. What it cannot derive it
refuses to invent. A missing decision stops the work and says which decision is missing.

Two lines matter here. The request is business intent, so it is recorded verbatim and becomes
the objective and, when nothing else supplies them, the acceptance criterion; quoting someone
is not inventing. Detail nobody stated - which endpoints, which fields, which provider, which
prices - is never filled in, and completion still needs evidence for every criterion, which is
what keeps a coarse request from passing as finished work.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from ..common import AgenticError
from .contracts import require

# A decision the system may not make for someone. Each one stops the work with the question
# that has to be answered, rather than with a guess nobody asked for.
DECISIONS = (
    "scope",
    "protected_contracts",
    "critical_risk",
    "conflicting_requirements",
)

# Gate names to the capability a verifier of that gate actually proves. The mapping is fixed
# and readable rather than clever: a gate whose name says nothing recognisable is static
# analysis, which is what an unclassified command usually is.
KINDS = (
    ("mutation", "test_strength"),
    ("integration", "integration"),
    ("acceptance", "acceptance"),
    ("property", "property"),
    ("coverage", "coverage"),
    ("security", "security"),
    ("architecture", "architecture"),
    ("migration", "migration_safety"),
    ("regression", "regression"),
    ("test", "unit"),
    ("spec", "unit"),
)
DEFAULT_KIND = "static_analysis"

# Kinds that speak for a criterion about behaviour. A linter and a coverage report are worth
# running and prove nothing about what the work is supposed to do, so they are recorded as
# verifiers that cite no criterion rather than as proof of every one.
BEHAVIOURAL = {"unit", "integration", "acceptance", "property", "regression", "migration_safety"}

# Words that carry no signal when matching a request against a project's own records.
STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "to",
    "for",
    "in",
    "on",
    "with",
    "that",
    "this",
    "add",
    "make",
    "create",
    "implement",
    "build",
    "fix",
    "update",
    "change",
    "please",
    "un",
    "una",
    "el",
    "la",
    "los",
    "las",
    "de",
    "del",
    "para",
    "con",
    "que",
    "y",
    "o",
    "implementa",
    "crea",
    "agrega",
    "arregla",
    "cambia",
    "haz",
    "por",
}
TERM = re.compile(r"[A-Za-z_][A-Za-z0-9_.\-/]{2,}")


def terms(request: str) -> list[str]:
    """The words worth searching for, lowercased, in the order they were written."""

    seen: list[str] = []
    for match in TERM.finditer(request):
        word = match.group(0).lower().strip(".-/")
        if word and word not in STOPWORDS and word not in seen:
            seen.append(word)
    return seen


def digest(request: str) -> str:
    """Identity of a request, so asking for the same thing twice finds the same task."""

    return hashlib.sha256(" ".join(request.lower().split()).encode()).hexdigest()[:16]


def _paths_in(request: str, known: set[str]) -> list[str]:
    """Paths the request names itself, which are the most reliable scope there is."""

    candidates = {match.group(0).strip(".,;:") for match in TERM.finditer(request)}
    return sorted(path for path in candidates if path in known)


def _from_knowledge(plane: Any, request: str, known: set[str]) -> list[str]:
    """Files the project's own index associates with the words of the request."""

    found: list[str] = []
    for term in terms(request)[:6]:
        try:
            entities = plane.knowledge.query(text=term, graph="code", limit=8)
        except (AgenticError, ValueError):
            continue
        for entity in entities:
            path = entity.get("path")
            if path and path in known and path not in found:
                found.append(path)
    return found[:12]


def _requirements(plane: Any, request: str) -> list[dict[str, Any]]:
    """Active requirements whose text overlaps the request, most specific first."""

    words = set(terms(request))
    matched = []
    for entity in plane.store.list("entity"):
        if entity.get("graph") != "requirement" or entity.get("lifecycle") != "ACTIVE":
            continue
        if entity.get("stale"):
            continue
        text = " ".join(str(entity.get(key, "")) for key in ("name", "statement", "excerpt"))
        overlap = words & set(terms(text))
        if overlap:
            matched.append((len(overlap), entity))
    return [entity for _, entity in sorted(matched, key=lambda pair: -pair[0])]


def _acceptance(request: str, requirements: list[dict[str, Any]]) -> tuple[list[str], str]:
    """Criteria from the project's requirements, or the request itself, said plainly."""

    criteria = [
        str(criterion)
        for requirement in requirements
        for criterion in requirement.get("acceptance", [])
        if str(criterion).strip()
    ]
    if criteria:
        return criteria, "the acceptance criteria recorded on the matched requirements"
    # The request is the business intent. Quoting it is not inventing one; what is never
    # filled in is detail nobody stated, and completion still needs evidence for this.
    return [request.strip()], "the request, recorded verbatim because nothing else states it"


def _verifiers(root: Path, criteria: int) -> tuple[list[dict[str, Any]], list[str], str]:
    """The project's own quality gates, as verifiers. Nothing else is invented to run."""

    from ..validation import load_quality_config

    path = next(
        (
            root / name
            for name in ("agentic.config.json", "agentic.config.example.json")
            if (root / name).is_file()
        ),
        None,
    )
    if path is None:
        return [], [], "no quality configuration to take verifiers from"
    try:
        config = load_quality_config(path)
    except AgenticError as exc:
        return [], [], f"the quality configuration cannot be read: {exc}"
    verifiers: list[dict[str, Any]] = []
    kinds: list[str] = []
    for gate in config["gates"]:
        if not isinstance(gate, dict) or not gate.get("required", True):
            continue
        command = gate["command"]
        argv = list(command) if isinstance(command, list) else command.split()
        if not argv:
            continue
        kind = _kind(str(gate.get("name", "")))
        cited = list(range(criteria)) if kind in BEHAVIOURAL else []
        verifiers.append({"kind": kind, "command": argv, "acceptance": cited})
        if kind not in kinds:
            kinds.append(kind)
    if not any(verifier["acceptance"] for verifier in verifiers):
        # Every criterion needs a verifier that speaks for it, and no gate here does. Which
        # command proves this work is the project's decision, not something to fabricate.
        return (
            [],
            [],
            (
                f"none of the required gates in {path.name} proves behaviour:"
                f" {', '.join(sorted({v['kind'] for v in verifiers})) or 'no gates at all'}"
            ),
        )
    return verifiers, kinds, f"the {len(verifiers)} required gates in {path.name}"


def _kind(name: str) -> str:
    lowered = name.lower()
    for token, kind in KINDS:
        if token in lowered:
            return kind
    return DEFAULT_KIND


def _risk(scope: list[str]) -> tuple[str, list[str]]:
    """The project's own risk rules, applied to the paths the work would touch.

    There is no diff yet, so the paths are all the signal there is; the level can only rise
    once the change exists, which is what the assurance engine recompiles against.
    """

    from ..risk import assess_risk

    assessment = assess_risk("", scope)
    signals = [name for name, present in assessment.factors.items() if present]
    return assessment.level, signals


def _dependencies(plane: Any, scope: list[str]) -> list[str]:
    """Open tasks that already own part of this scope. Overlapping work waits, not races."""

    owned = set(scope)
    return sorted(
        task["id"]
        for task in plane.store.list("task")
        if task["state"] not in {"COMPLETED", "CANCELLED"} and owned & set(task["scope"])
    )


def _protected(plane: Any, scope: list[str]) -> list[str]:
    policy = plane.policy()
    protected = [str(path) for path in policy["protected_paths"]]
    return sorted(
        path
        for path in scope
        if any(path == item or path.startswith(item.rstrip("/") + "/") for item in protected)
    )


def derive(plane: Any, request: str) -> dict[str, Any]:
    """A task contract for this request, or the decisions that have to be made first."""

    require(bool(request.strip()), "INVALID_REQUEST", "Describe the work in your own words")
    root = Path(plane.root)
    known = {
        str(entity["path"])
        for entity in plane.store.list("entity")
        if entity.get("graph") == "code" and entity.get("path") and not entity.get("stale")
    }
    named = _paths_in(request, known)
    scope = named or _from_knowledge(plane, request, known)
    requirements = _requirements(plane, request)
    acceptance, acceptance_source = _acceptance(request, requirements)
    verifiers, kinds, verifier_source = _verifiers(root, len(acceptance))
    risk, signals = _risk(scope)
    protected = _protected(plane, scope)
    decisions: list[dict[str, str]] = []
    if not scope:
        decisions.append(
            {
                "decision": "scope",
                "question": "Which files or directories may this work change?",
                "why": "nothing in the request names a path, and the project's index does not"
                " associate its words with any file, so there is no bounded scope to authorise",
            }
        )
    if protected:
        decisions.append(
            {
                "decision": "protected_contracts",
                "question": f"Do you authorise changing {', '.join(protected)}?",
                "why": "these are protected contracts, and only a contract-authorised role may"
                " change them",
            }
        )
    if risk == "CRITICAL":
        decisions.append(
            {
                "decision": "critical_risk",
                "question": "Do you accept this as CRITICAL work, and who signs it off?",
                "why": "the project's own risk rules classify this scope as CRITICAL, which"
                f" requires explicit human acceptance: {', '.join(signals) or 'critical paths'}",
            }
        )
    if not verifiers:
        decisions.append(
            {
                "decision": "conflicting_requirements",
                "question": "Which command proves this work?",
                "why": verifier_source,
            }
        )
    contract = {
        "objective": request.strip(),
        "scope": scope,
        "out_of_scope": ["anything outside the recorded scope", "protected contracts"],
        "requirements": [str(entity["id"]) for entity in requirements],
        "acceptance": acceptance,
        "dependencies": _dependencies(plane, scope),
        "boundaries": [],
        "context": [f"request digest {digest(request)}", f"acceptance from {acceptance_source}"],
        "verification": verifiers,
        "required_evidence": kinds,
        "rollback": "revert the changes this task made to its scope; nothing outside it was"
        " authorised, and no deployment or migration is part of this task",
        "definition_of_done": "every acceptance criterion has current passing evidence and a"
        " checkpoint records the work",
        "risk": risk,
        # Bounded by default, and by the scope it was given: a task that may touch twice as
        # many files as it declared is not a bounded task. Nothing external, nothing paid for.
        "budget": {
            "max_runtime": 1800,
            "max_retries": 3,
            "max_files": max(len(scope) * 2, 4),
            "max_lines": 2000,
            "max_external_calls": 0,
            "max_cost": 0,
        },
    }
    return {
        "contract": contract,
        "decisions": decisions,
        "provenance": {
            "request": request.strip(),
            "digest": digest(request),
            "scope_from": "paths named in the request"
            if named
            else "the project's knowledge index",
            "acceptance_from": acceptance_source,
            "verifiers_from": verifier_source,
            "requirements_matched": [str(entity["id"]) for entity in requirements],
            "risk_signals": signals,
        },
    }


def _existing(plane: Any, request: str, scope: list[str]) -> dict[str, Any] | None:
    """The task that already represents this work, when there is one.

    Identity first: the same words asked twice are the same request. Then an open task whose
    scope this request falls inside, which is the case where someone rephrases what they asked
    for a moment ago.
    """

    wanted = digest(request)
    open_tasks = [
        task for task in plane.store.list("task") if task["state"] not in {"COMPLETED", "CANCELLED"}
    ]
    for task in open_tasks:
        if any(f"request digest {wanted}" == line for line in task.get("context", [])):
            return {"task": task, "matched_by": "the same request was made before"}
    if not scope:
        return None
    for task in open_tasks:
        if set(scope) <= set(task["scope"]):
            return {
                "task": task,
                "matched_by": f"an open task already covers this scope: {task['objective']}",
            }
    return None


def _approve_gates(plane: Any, verifiers: list[dict[str, Any]]) -> list[list[str]]:
    """Approve exactly the commands the project's own quality configuration declares.

    The command allow-list is a security boundary, and this does not widen it: a gate in
    `agentic.config.json` was written by the project, so running it is already its decision.
    Nothing else is approved, and each approval is in the audit chain.
    """

    approved = [list(command) for command in plane.policy()["allowed_commands"]]
    added: list[list[str]] = []
    for verifier in verifiers:
        command = list(verifier["command"])
        if command not in approved:
            plane.approve_command(command)
            approved.append(command)
            added.append(command)
    return added


def start(
    plane: Any,
    request: str,
    *,
    agent: str = "local-agent",
    capabilities: list[str] | None = None,
    claim: bool = True,
) -> dict[str, Any]:
    """Turn a request into governed work: link or derive, make ready, join and claim.

    Every step is one the user would otherwise have had to know about. None of them invents
    business intent, and a decision that is genuinely theirs stops the whole thing.
    """

    from . import preflight

    flight = preflight.run(plane.root)
    preflight.requires(flight)

    derived = derive(plane, request)
    contract = derived["contract"]
    linked = _existing(plane, request, contract["scope"])
    if linked is not None:
        task = linked["task"]
        return _report(
            plane,
            flight,
            derived,
            task,
            linked["matched_by"],
            [],
            claim=claim,
            agent=agent,
            capabilities=capabilities,
        )
    if derived["decisions"]:
        return {
            "status": "BLOCKED",
            "state": "BLOCKED",
            "request": request.strip(),
            "preflight": flight,
            "task": None,
            "decisions": derived["decisions"],
            "provenance": derived["provenance"],
            "reason": "this work needs a decision that is not the system's to make",
        }
    approved = _approve_gates(plane, contract["verification"])
    task = plane.create_task(contract)
    with plane.store.transaction():
        plane.store.put(
            "work_request",
            {
                "task_id": task["id"],
                "request": request.strip(),
                "digest": digest(request),
                "provenance": derived["provenance"],
                "created_at": time.time(),
            },
        )
        plane.store.event(
            "local-owner",
            "work.derive",
            {"task": task["id"], "digest": digest(request), **derived["provenance"]},
        )
    return _report(
        plane,
        flight,
        derived,
        task,
        "derived from this request",
        approved,
        claim=claim,
        agent=agent,
        capabilities=capabilities,
    )


def _readiness(plane: Any, task: dict[str, Any]) -> dict[str, Any]:
    """READY, WAITING or BLOCKED, and which of the three for a reason.

    An unfinished dependency is waiting: the work exists and its turn has not come. Anything
    else the plane refuses is blocked, and the refusal is the reason.
    """

    report = plane.readiness(task["id"])
    reasons = report.get("reasons", [])
    pending = [plane.store.get(identifier, "task") for identifier in task["dependencies"]]
    waiting = [item["id"] for item in pending if item["state"] != "COMPLETED"]
    if report["status"] == "READY":
        return {"state": "READY", "reasons": [], "waiting_for": []}
    if waiting and all(reason.get("type") == "dependency" for reason in reasons):
        return {"state": "WAITING", "reasons": reasons, "waiting_for": waiting}
    return {"state": "BLOCKED", "reasons": reasons, "waiting_for": waiting}


def _held_elsewhere(plane: Any, task_id: str) -> str | None:
    """The task that already owns this working tree, when there is one.

    Two claims at once are only safe in isolated workspaces with disjoint contracts, which is
    a 2.0 invariant and a good one. Rather than create a worktree nobody asked for, the task
    is recorded and readied and the claim waits: one tree, one claim, and the report says so.
    """

    for lease in plane.store.list("lease"):
        if lease["state"] != "ACTIVE" or lease["task_id"] == task_id:
            continue
        other = plane.store.get(lease["task_id"], "task")
        if not other.get("workspace_id"):
            return str(lease["task_id"])
    return None


def _report(
    plane: Any,
    flight: dict[str, Any],
    derived: dict[str, Any],
    task: dict[str, Any],
    matched_by: str,
    approved: list[list[str]],
    *,
    claim: bool,
    agent: str,
    capabilities: list[str] | None,
) -> dict[str, Any]:
    state = _readiness(plane, task)
    session: str | None = None
    lease: dict[str, Any] | None = None
    if state["state"] == "READY" and task["state"] == "PLANNED":
        plane.ready(task["id"])
        task = plane.store.get(task["id"], "task")
    held = _held_elsewhere(plane, task["id"])
    if claim and state["state"] == "READY" and task["state"] == "READY" and not held:
        joined = plane.join(agent, capabilities or ["code"])
        session = str(joined["session"])
        lease = plane.claim(task["id"], session)
        task = plane.store.get(task["id"], "task")
    if held and state["state"] == "READY":
        state = {
            **state,
            "state": "WAITING",
            "waiting_for": [held],
            "reasons": [{"type": "working_tree_claimed", "task_id": held}],
        }
    return {
        "status": "PASS" if state["state"] == "READY" else "BLOCKED",
        "state": state["state"],
        "request": derived["provenance"]["request"],
        "preflight": flight,
        "task": task,
        "matched_by": matched_by,
        "readiness": state,
        "approved_commands": approved,
        "session": session,
        "lease": lease,
        "decisions": [],
        "provenance": derived["provenance"],
        "reason": {
            "READY": "the task is claimed and the work may proceed",
            "WAITING": f"the task is recorded and waits for {held}, which holds this working tree"
            if held
            else "the task is recorded and waits for the work it depends on",
            "BLOCKED": "the task is recorded and cannot start yet",
        }[state["state"]],
    }


def render(result: dict[str, Any]) -> str:
    """What the person asking for the work should see about how it was set up."""

    lines = [f"Work state: {result['state']}", ""]
    task = result.get("task")
    if task:
        lines += [
            f"  Task       {task['id']} ({task['state']})",
            f"  Objective  {task['objective']}",
            f"  Scope      {', '.join(task['scope'])}",
            f"  Risk       {task['risk']}",
            f"  Evidence   {', '.join(task['required_evidence'])}",
            f"  Matched    {result['matched_by']}",
        ]
        if result.get("session"):
            lines.append("  Claimed    yes, with a lease")
    provenance = result.get("provenance", {})
    if provenance:
        lines += [
            "",
            "Derived from:",
            f"  scope       {provenance['scope_from']}",
            f"  acceptance  {provenance['acceptance_from']}",
            f"  verifiers   {provenance['verifiers_from']}",
        ]
    if result["decisions"]:
        lines += ["", "Waiting on a decision that is yours to make:"]
        for decision in result["decisions"]:
            lines += [f"  - {decision['question']}", f"    Why: {decision['why']}"]
    if result.get("readiness", {}).get("reasons"):
        lines += ["", "Not ready because:"]
        lines += [
            f"  - {json.dumps(reason, sort_keys=True)}" for reason in result["readiness"]["reasons"]
        ]
    lines += ["", f"Reason: {result['reason']}"]
    return "\n".join(lines)
