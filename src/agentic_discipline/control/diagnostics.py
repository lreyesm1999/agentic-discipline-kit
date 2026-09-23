"""Compose existing installation diagnostics with transactional control health."""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

from .plane import Plane


def doctor(plane: Plane) -> dict[str, Any]:
    from .assurance.service import integrity

    result = subprocess.run(
        [sys.executable, "-m", "agentic_discipline", "doctor", "--json"],
        cwd=plane.root,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    installation = json.loads(result.stdout)
    audit = plane.store.audit()
    # The assurance invariants are part of project health: an obligation that disappeared or
    # a completed task that lost its proof is a finding, not something to discover later.
    assurance = integrity(plane)
    healthy = result.returncode == 0 and audit["status"] == "PASS" and assurance["status"] != "FAIL"
    return {
        "status": "PASS" if healthy else "FAIL",
        "installation": installation,
        "control_audit": audit,
        "assurance_integrity": assurance,
    }
