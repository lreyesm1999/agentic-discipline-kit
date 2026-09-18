"""Compose existing installation diagnostics with transactional control health."""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

from .plane import Plane


def doctor(plane: Plane) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-m", "agentic_discipline", "doctor"],
        cwd=plane.root,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    installation = json.loads(result.stdout)
    audit = plane.store.audit()
    return {
        "status": "PASS" if result.returncode == 0 and audit["status"] == "PASS" else "FAIL",
        "installation": installation,
        "control_audit": audit,
    }
