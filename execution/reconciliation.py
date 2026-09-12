"""Fail-closed execution reconciliation for SHREEK V5.1.

The reconciler compares an immutable order intent with an observed execution
report. It never sends, modifies, or closes broker orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isclose, isfinite

from core.enums import Direction


@dataclass(frozen=True)
class OrderIntent:
    order_id: str
    symbol: str
    direction: Direction
    volume: float
    expected_price: float


@dataclass(frozen=True)
class ExecutionReport:
    order_id: str
    symbol: str
    direction: Direction
    volume: float
    fill_price: float


@dataclass(frozen=True)
class ReconciliationResult:
    matched: bool
    reasons: tuple[str, ...]


def reconcile_execution(
    intent: OrderIntent,
    report: ExecutionReport,
    *,
    price_tolerance: float = 0.0,
    volume_tolerance: float = 0.0,
) -> ReconciliationResult:
    """Return a deterministic match result; any invalid/mismatched field fails closed."""
    if not isinstance(intent, OrderIntent) or not isinstance(report, ExecutionReport):
        raise TypeError("intent and report must use the reconciliation models")
    if not isfinite(price_tolerance) or price_tolerance < 0:
        raise ValueError("price_tolerance must be finite and non-negative")
    if not isfinite(volume_tolerance) or volume_tolerance < 0:
        raise ValueError("volume_tolerance must be finite and non-negative")

    reasons: list[str] = []
    if not intent.order_id or report.order_id != intent.order_id:
        reasons.append("order identity mismatch")
    if report.symbol != intent.symbol:
        reasons.append("symbol mismatch")
    if report.direction is not intent.direction:
        reasons.append("direction mismatch")
    if not isfinite(intent.volume) or intent.volume <= 0 or not isfinite(report.volume) or report.volume <= 0:
        reasons.append("invalid volume")
    elif not isclose(report.volume, intent.volume, rel_tol=0.0, abs_tol=volume_tolerance):
        reasons.append("volume mismatch")
    if not isfinite(intent.expected_price) or intent.expected_price <= 0 or not isfinite(report.fill_price) or report.fill_price <= 0:
        reasons.append("invalid execution price")
    elif not isclose(report.fill_price, intent.expected_price, rel_tol=0.0, abs_tol=price_tolerance):
        reasons.append("fill price outside tolerance")

    return ReconciliationResult(not reasons, tuple(reasons))
