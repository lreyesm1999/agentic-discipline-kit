"""Adaptive Assurance Engine.

Every change creates proof obligations. A task is complete only when all required proof
obligations are resolved by current evidence.
"""

from .decision import decide, mandatory_debt
from .model import RESOLVED, STATUSES, obligation_id
from .registry import Registry
from .resolver import debt, obligation_binding, obligations_for, resolve

__all__ = [
    "RESOLVED",
    "Registry",
    "STATUSES",
    "debt",
    "decide",
    "mandatory_debt",
    "obligation_binding",
    "obligation_id",
    "obligations_for",
    "resolve",
]
