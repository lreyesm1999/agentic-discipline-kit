"""Specialized graphs with provenance, reconciliation and historical dispositions."""

from __future__ import annotations

from collections import deque
from typing import Any

from .contracts import (
    AUTHORITIES,
    GRAPHS,
    LIFECYCLES,
    RELATIONS,
    digest,
    entity_contract,
    require,
    uid,
)
from .store import Store


class Knowledge:
    def __init__(self, store: Store) -> None:
        self.store = store

    def apply(
        self, changes: list[dict[str, Any]], base_version: int, reason: str, actor: str = "local"
    ) -> dict[str, Any]:
        require(
            bool(reason.strip()) and bool(changes),
            "INVALID_CHANGESET",
            "Reason and changes are required",
        )
        with self.store.transaction():
            require(
                self.store.knowledge_version == base_version,
                "VERSION_CONFLICT",
                "Knowledge version changed; reconcile before retry",
            )
            self.store.bump()
            entities = []
            for change in changes:
                data = dict(change)
                expected = data.pop("expected_version", None)
                entity_contract(data)
                data.setdefault("lifecycle", "ACTIVE")
                data.setdefault("stale", False)
                if data.get("id"):
                    previous = self.store.get(data["id"], "entity")
                    require(
                        not (previous["lifecycle"] != "ACTIVE" and data["lifecycle"] == "ACTIVE"),
                        "RESURRECTION_BLOCKED",
                        "Retired identities cannot be implicitly reactivated; create an explicit reviewed replacement",
                    )
                entities.append(self.store.put("entity", data, expected=expected, actor=actor))
            for edge in self.store.db.execute(
                "SELECT source,target FROM edges WHERE relation='depends_on'"
            ):
                left, right = self.store.get(edge[0], "entity"), self.store.get(edge[1], "entity")
                require(
                    left["lifecycle"] != "ACTIVE" or right["lifecycle"] == "ACTIVE",
                    "RETIRED_DEPENDENCY",
                    "Retire or replace active dependents in the same changeset",
                )
            record = self.store.put(
                "changeset",
                {
                    "base_version": base_version,
                    "reason": reason,
                    "actor": actor,
                    "entities": [e["id"] for e in entities],
                    "status": "APPLIED",
                },
                actor=actor,
            )
            return {
                "changeset": record,
                "entities": entities,
                "knowledge_version": self.store.knowledge_version,
            }

    def link(self, source: str, target: str, relation: str) -> dict[str, Any]:
        require(
            relation in RELATIONS and source != target,
            "INVALID_EDGE",
            "Unknown relation or self edge",
        )
        with self.store.transaction():
            left, right = self.store.get(source, "entity"), self.store.get(target, "entity")
            if relation == "depends_on":
                require(
                    not (left["lifecycle"] == "ACTIVE" and right["lifecycle"] != "ACTIVE"),
                    "RETIRED_DEPENDENCY",
                    "Active knowledge cannot depend on retired knowledge",
                )
                # The list grows while it is walked, so the walk ends once no new node is
                # reached; unlike popping, nothing can keep it from ever shrinking.
                visited, pending = set(), [target]
                for current in pending:
                    if current in visited:
                        continue
                    visited.add(current)
                    pending.extend(
                        r[0]
                        for r in self.store.db.execute(
                            "SELECT target FROM edges WHERE source=? AND relation='depends_on'",
                            (current,),
                        )
                    )
                require(source not in visited, "CYCLE", "Dependency cycle")
            rules = {
                "implemented_by": {"code"},
                "verified_by": {"evidence"},
                "claimed_by": {"execution"},
                "evidenced_by": {"evidence"},
                "blocked_by": {"decision"},
            }
            if relation in rules:
                require(
                    right["graph"] in rules[relation],
                    "INVALID_EDGE",
                    "Relationship target belongs to a different graph",
                )
            existing = self.store.db.execute(
                "SELECT * FROM edges WHERE source=? AND target=? AND relation=?",
                (source, target, relation),
            ).fetchone()
            if existing:
                return dict(existing)
            identifier = uid("EDGE")
            self.store.db.execute(
                "INSERT INTO edges VALUES (?,?,?,?)", (identifier, source, target, relation)
            )
            self.store.bump()
            self.store.event(
                "local",
                "edge.add",
                {"id": identifier, "source": source, "target": target, "relation": relation},
            )
            return {"id": identifier, "source": source, "target": target, "relation": relation}

    def query(
        self,
        text: str = "",
        graph: str | None = None,
        historical: bool = False,
        limit: int = 50,
        at_version: int | None = None,
    ) -> list[dict[str, Any]]:
        require(
            1 <= limit <= 500 and (graph is None or graph in GRAPHS),
            "INVALID_QUERY",
            "Invalid graph or limit",
        )
        require(
            at_version is None
            or (type(at_version) is int and 0 <= at_version <= self.store.knowledge_version),
            "INVALID_QUERY",
            "Unknown knowledge revision",
        )
        entities = (
            self.store.list("entity") if at_version is None else self.store.entities_at(at_version)
        )
        matches = None
        if text.strip() and at_version is None:
            # Literal phrases prevent FTS syntax from becoming a second query language.
            term = '"' + text.replace('"', '""') + '"'
            matches = {
                r[0]
                for r in self.store.db.execute(
                    "SELECT id FROM search WHERE search MATCH ?", (term,)
                )
            }
        return [
            e
            for e in entities
            if (matches is None or e["id"] in matches)
            and (at_version is None or text.casefold() in str(e).casefold())
            and (graph is None or e["graph"] == graph)
            and (historical or (e["lifecycle"] == "ACTIVE" and not e.get("stale")))
        ][:limit]

    def impact(
        self, identifier: str, direction: str = "in", depth: int = 4
    ) -> list[dict[str, Any]]:
        self.store.get(identifier, "entity")
        require(
            direction in {"in", "out"} and 0 <= depth <= 20, "INVALID_QUERY", "Invalid traversal"
        )
        edges = list(self.store.db.execute("SELECT * FROM edges"))
        visited = {identifier}
        queue = deque([(identifier, 0)])
        while queue:
            current, level = queue.popleft()
            if level == depth:
                continue
            for edge in edges:
                src, dst = (
                    (edge["source"], edge["target"])
                    if direction == "out"
                    else (edge["target"], edge["source"])
                )
                if src == current and dst not in visited:
                    visited.add(dst)
                    queue.append((dst, level + 1))
        return [self.store.get(i, "entity") for i in sorted(visited - {identifier})]

    def claim(self, data: dict[str, Any]) -> dict[str, Any]:
        require(
            {
                "subject",
                "predicate",
                "value",
                "source_ref",
                "authority",
                "confidence",
                "observation",
            }
            <= data.keys(),
            "INVALID_CLAIM",
            "Claim lacks provenance or statement",
        )
        self.store.get(data["subject"], "entity")
        entity_contract(
            {**data, "graph": "requirement", "type": "claim", "name": str(data["predicate"])}
        )
        require(
            data["observation"] != "VERIFIED" or data.get("evidence_refs"),
            "UNPROVEN_CLAIM",
            "Verified claims require evidence references",
        )
        for identifier in data.get("evidence_refs", []):
            evidence = self.store.get(identifier, "evidence")
            from pathlib import Path

            from .plane import Plane
            from .verification import binding, fresh

            task = self.store.get(evidence["task_id"], "task")
            require(
                data["subject"] in task["requirements"]
                and data.get("acceptance_index") in evidence["acceptance"],
                "UNRELATED_EVIDENCE",
                "Claim must cite an acceptance criterion for its requirement",
            )
            with Plane(Path(self.store.list("project")[0]["root"])) as plane:
                require(
                    evidence["result"] == "PASS"
                    and not evidence.get("stale")
                    and fresh(plane, evidence, binding(plane, task)),
                    "UNPROVEN_CLAIM",
                    "Claim evidence is not current or its artifact was changed",
                )
        with self.store.transaction():
            conflicts = [
                c
                for c in self.store.list("claim")
                if c["subject"] == data["subject"]
                and c["predicate"] == data["predicate"]
                and c["disposition"] in {"CANONICAL", "CANDIDATE", "CONFLICTING"}
                and digest(c["value"]) != digest(data["value"])
            ]
            eligible = data["observation"] == "VERIFIED" or data["authority"] in {
                "human",
                "contract",
            }
            higher = any(
                AUTHORITIES[c["authority"]] >= AUTHORITIES[data["authority"]] for c in conflicts
            )
            subject = self.store.get(data["subject"], "entity")
            canonical = eligible and not higher and subject["lifecycle"] == "ACTIVE"
            claim = self.store.put(
                "claim",
                {
                    **data,
                    "conflicts": [c["id"] for c in conflicts],
                    "disposition": "CANONICAL"
                    if canonical
                    else "REJECTED"
                    if any(
                        c["disposition"] == "CANONICAL"
                        and AUTHORITIES[c["authority"]] > AUTHORITIES[data["authority"]]
                        for c in conflicts
                    )
                    else "CONFLICTING"
                    if conflicts
                    else "CANDIDATE",
                },
            )
            for old in conflicts:
                if AUTHORITIES[old["authority"]] > AUTHORITIES[data["authority"]]:
                    continue
                self.store.put(
                    "claim",
                    {
                        **old,
                        "conflicts": list(set(old["conflicts"] + [claim["id"]])),
                        "disposition": "SUPERSEDED" if canonical else "CONFLICTING",
                    },
                    expected=old["version"],
                )
            self.store.bump()
            return claim

    def resolve_claim(self, identifier: str, reason: str) -> dict[str, Any]:
        require(
            bool(reason.strip()), "DECISION_REQUIRED", "Claim resolution needs an owner decision"
        )
        with self.store.transaction():
            claim = self.store.get(identifier, "claim")
            subject = self.store.get(claim["subject"], "entity")
            require(
                subject["lifecycle"] == "ACTIVE" and not subject.get("stale"),
                "STALE_CONTEXT",
                "Cannot promote retired or stale intent",
            )
            for other in self.store.list("claim"):
                if (
                    other["id"] != identifier
                    and other["subject"] == claim["subject"]
                    and other["predicate"] == claim["predicate"]
                ):
                    self.store.put(
                        "claim",
                        {**other, "disposition": "SUPERSEDED"},
                        expected=other["version"],
                        actor="local-owner",
                    )
            self.store.bump()
            self.store.put(
                "decision",
                {
                    "claim_id": identifier,
                    "reason": reason,
                    "state": "DECIDED",
                    "authority": "human",
                },
                actor="local-owner",
            )
            return self.store.put(
                "claim",
                {
                    **claim,
                    "disposition": "CANONICAL",
                    "original_authority": claim["authority"],
                    "authority": "human",
                    "observation": "DECLARED",
                    "evidence_refs": [],
                    "resolution_reason": reason,
                },
                expected=claim["version"],
                actor="local-owner",
            )

    def lifecycle(self, identifier: str, state: str, reason: str) -> dict[str, Any]:
        require(
            state in LIFECYCLES - {"ACTIVE"} and bool(reason.strip()),
            "INVALID_LIFECYCLE",
            "A non-active state and reason are required",
        )
        entity = self.store.get(identifier, "entity")
        result = self.apply(
            [
                {
                    **entity,
                    "lifecycle": state,
                    "lifecycle_reason": reason,
                    "expected_version": entity["version"],
                }
            ],
            self.store.knowledge_version,
            reason,
        )
        return {**result, "affected": self.impact(identifier)}
