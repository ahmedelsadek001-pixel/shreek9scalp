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
    elif not reconciliation.matched:
        reasons.extend("reconciliation: " + reason for reason in reconciliation.reasons)
        if not reconciliation.reasons:
            reasons.append("reconciliation: rejected without reason")

    if not isinstance(quality, ExecutionQualityDecision):
        reasons.append("execution quality result malformed")
    elif not quality.allowed:
        reasons.extend("quality: " + reason for reason in quality.reasons)
        if not quality.reasons:
            reasons.append("quality: rejected without reason")

    return PostTradeDecision(not reasons, tuple(reasons))
