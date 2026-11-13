"""Fail-closed V6.0 evidence-completeness helper.

Boolean claims can establish only that required fields are present and true.
They cannot authenticate their producer and never grant final release/live
authority. This module cannot connect to MT5 or send orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


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
    requirements_satisfied: bool = False


def evaluate_live_authorization(evidence: Mapping[str, bool]) -> LiveAuthorization:
    """Evaluate claim completeness without granting final authorization."""
    if not isinstance(evidence, Mapping):
        raise TypeError("evidence must be a mapping")

    missing = []
    for key in REQUIRED_EVIDENCE:
        value = evidence.get(key, False)
        if type(value) is not bool or value is not True:
            missing.append(key)
    complete = not missing
    return LiveAuthorization(False, tuple(missing), complete)


def require_live_authorization(evidence: Mapping[str, bool]) -> None:
    """Never authorize self-asserted flags without independent authenticity proof."""
    result = evaluate_live_authorization(evidence)
    if not result.requirements_satisfied:
        raise RuntimeError("live authorization blocked; missing evidence: " + ", ".join(result.missing))
    raise RuntimeError(
        "live authorization blocked; independent evidence authenticity verification is not implemented"
    )
