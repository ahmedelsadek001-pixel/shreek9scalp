"""Fail-closed V5.3 execution-safety evidence gate.

This module evaluates evidence about paper/shadow execution controls only. It
never authorizes MT5, opens a broker connection, or sends an order.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionSafetyEvidence:
    quote_safety_validated: bool
    idempotency_validated: bool
    outcome_classification_validated: bool
    reconciliation_validated: bool
    recovery_validated: bool
    journal_integrity_validated: bool
    live_execution_disabled: bool


@dataclass(frozen=True)
class ExecutionSafetyDecision:
    ready: bool
    failures: tuple[str, ...]


def evaluate_execution_safety(evidence: ExecutionSafetyEvidence) -> ExecutionSafetyDecision:
    """Require every V5.3 control and the live-disabled invariant explicitly."""
    if not isinstance(evidence, ExecutionSafetyEvidence):
        raise TypeError("evidence must be ExecutionSafetyEvidence")
    checks = {
        "quote safety is not validated": evidence.quote_safety_validated,
        "idempotency is not validated": evidence.idempotency_validated,
        "broker outcome classification is not validated": evidence.outcome_classification_validated,
        "execution reconciliation is not validated": evidence.reconciliation_validated,
        "disconnect/recovery is not validated": evidence.recovery_validated,
        "execution journal integrity is not validated": evidence.journal_integrity_validated,
        "live execution is not explicitly disabled": evidence.live_execution_disabled,
    }
    failures = tuple(reason for reason, passed in checks.items() if type(passed) is not bool or not passed)
    return ExecutionSafetyDecision(not failures, failures)


def require_execution_safety(evidence: ExecutionSafetyEvidence) -> None:
    """Raise instead of allowing an incomplete V5.3 evidence package."""
    decision = evaluate_execution_safety(evidence)
    if not decision.ready:
        raise RuntimeError("V5.3 execution-safety gate blocked: " + "; ".join(decision.failures))
