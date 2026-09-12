"""Final fail-closed release gate for SHREEK V5.1.

This module validates readiness evidence only. It never enables broker execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class ReleaseEvidence:
    ci_green: bool
    tests_green: bool
    data_integrity_validated: bool
    walk_forward_passed: bool
    robustness_passed: bool
    paper_trading_validated: bool
    security_reviewed: bool
    execution_reconciled: bool
    shadow_validated: bool = False


@dataclass(frozen=True)
class ReleaseDecision:
    ready: bool
    failures: tuple[str, ...]


def evaluate_release(evidence: ReleaseEvidence) -> ReleaseDecision:
    """Return release readiness; every required control must explicitly pass."""
    if not isinstance(evidence, ReleaseEvidence):
        raise TypeError("evidence must be ReleaseEvidence")
    checks: Mapping[str, bool] = {
        "CI is not green": evidence.ci_green,
        "test suite is not green": evidence.tests_green,
        "market-data integrity is not validated": evidence.data_integrity_validated,
        "walk-forward validation has not passed": evidence.walk_forward_passed,
        "robustness validation has not passed": evidence.robustness_passed,
        "paper trading has not been validated": evidence.paper_trading_validated,
        "security review has not passed": evidence.security_reviewed,
        "execution reconciliation has not passed": evidence.execution_reconciled,
        "shadow execution has not been validated": evidence.shadow_validated,
    }
    failures = tuple(reason for reason, passed in checks.items() if type(passed) is not bool or not passed)
    return ReleaseDecision(ready=not failures, failures=failures)


def require_release_ready(evidence: ReleaseEvidence) -> None:
    """Fail closed when any release prerequisite is missing or false."""
    decision = evaluate_release(evidence)
    if not decision.ready:
        raise RuntimeError("V5.1 release gate blocked: " + "; ".join(decision.failures))
