"""Fail-closed post-trade safety gate for SHREEK V5.3.

The post-trade boundary accepts only observed, validated results. It never
routes orders, changes positions, or retries broker operations.
"""
from __future__ import annotations

from dataclasses import dataclass

from execution.quality_gate import ExecutionQualityDecision
from execution.reconciliation import ReconciliationResult


@dataclass(frozen=True)
class PostTradeDecision:
    accepted: bool
    reasons: tuple[str, ...]


def evaluate_post_trade(
    *,
    reconciliation: ReconciliationResult,
    quality: ExecutionQualityDecision,
) -> PostTradeDecision:
    """Accept a fill only when identity and execution-quality checks both pass."""
    reasons: list[str] = []

    if not isinstance(reconciliation, ReconciliationResult):
        reasons.append("reconciliation result malformed")
    elif type(reconciliation.matched) is not bool:
        reasons.append("reconciliation result malformed")
    elif not isinstance(reconciliation.reasons, tuple) or any(
        not isinstance(reason, str) for reason in reconciliation.reasons
    ):
        reasons.append("reconciliation reasons malformed")
    elif reconciliation.matched and reconciliation.reasons:
        reasons.append("reconciliation decision internally inconsistent")
    elif not reconciliation.matched:
        reasons.extend("reconciliation: " + reason for reason in reconciliation.reasons)
        if not reconciliation.reasons:
            reasons.append("reconciliation: rejected without reason")

    if not isinstance(quality, ExecutionQualityDecision):
        reasons.append("execution quality result malformed")
    elif type(quality.allowed) is not bool:
        reasons.append("execution quality result malformed")
    elif not isinstance(quality.reasons, tuple) or any(
        not isinstance(reason, str) for reason in quality.reasons
    ):
        reasons.append("execution quality reasons malformed")
    elif quality.allowed and quality.reasons:
        reasons.append("execution quality decision internally inconsistent")
    elif not quality.allowed:
        reasons.extend("quality: " + reason for reason in quality.reasons)
        if not quality.reasons:
            reasons.append("quality: rejected without reason")

    return PostTradeDecision(not reasons, tuple(reasons))
