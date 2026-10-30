"""Final fail-closed authorization gate for SHREEK V6.0.

The gate only evaluates explicit evidence flags. It cannot connect to MT5,
send orders, size positions, or override any earlier safety layer.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


# V5.1 release prerequisites plus the V6.0 broker/operator controls.
# Keep this list explicit: missing evidence must never become an implicit pass.
REQUIRED_EVIDENCE = (
    "ci_green",
    "tests_green",
    "data_integrity_validated",
    "walk_forward_passed",
    "robustness_passed",
    "paper_trading_validated",
    "security_reviewed",
    "execution_reconciled",
    "shadow_validated",
    "recovery_validated",
    "broker_validation",
    "operator_approval",
)


@dataclass(frozen=True)
class LiveAuthorization:
    authorized: bool
    missing: tuple[str, ...]


def evaluate_live_authorization(evidence: Mapping[str, bool]) -> LiveAuthorization:
    """Authorize only when every mandatory evidence item is explicitly True."""
    if not isinstance(evidence, Mapping):
        raise TypeError("evidence must be a mapping")

    missing = []
    for key in REQUIRED_EVIDENCE:
        value = evidence.get(key, False)
        if type(value) is not bool or value is not True:
            missing.append(key)
    return LiveAuthorization(not missing, tuple(missing))


def require_live_authorization(evidence: Mapping[str, bool]) -> None:
    """Raise instead of allowing a caller to proceed with incomplete evidence."""
    result = evaluate_live_authorization(evidence)
    if not result.authorized:
        raise RuntimeError("live authorization blocked; missing evidence: " + ", ".join(result.missing))
