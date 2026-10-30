"""Fail-closed execution quality gate for SHREEK V5.3.

This layer evaluates an observed execution snapshot against explicit limits.
It has no broker transport authority and never sends or modifies orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class ExecutionQualityPolicy:
    max_abs_slippage: float
    max_spread: float
    max_latency_ms: float

    def validate(self) -> None:
        values = (self.max_abs_slippage, self.max_spread, self.max_latency_ms)
        if any(not isfinite(float(value)) for value in values):
            raise ValueError("execution quality limits must be finite")
        if any(float(value) < 0 for value in values):
            raise ValueError("execution quality limits must be non-negative")


@dataclass(frozen=True)
class ExecutionQualityDecision:
    allowed: bool
    reasons: tuple[str, ...]


def evaluate_quality(
    policy: ExecutionQualityPolicy,
    *,
    expected_price: float,
    fill_price: float,
    spread: float,
    latency_ms: float,
) -> ExecutionQualityDecision:
    """Evaluate execution observations against policy limits; fail closed."""
    policy.validate()
    values = (expected_price, fill_price, spread, latency_ms)
    if not all(isfinite(float(value)) for value in values):
        return ExecutionQualityDecision(False, ("execution observations must be finite",))
    if expected_price <= 0 or fill_price <= 0:
        return ExecutionQualityDecision(False, ("execution prices must be positive",))
    if spread < 0 or latency_ms < 0:
        return ExecutionQualityDecision(False, ("spread and latency must be non-negative",))

    reasons: list[str] = []
    slippage = abs(fill_price - expected_price)
    if slippage > policy.max_abs_slippage:
        reasons.append("slippage outside limit")
    if spread > policy.max_spread:
        reasons.append("spread outside limit")
    if latency_ms > policy.max_latency_ms:
        reasons.append("latency outside limit")
    return ExecutionQualityDecision(not reasons, tuple(reasons))
