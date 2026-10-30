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


def _is_finite_number(value: object) -> bool:
    """Accept only real built-in numeric inputs that can be compared safely."""
    if type(value) not in (int, float):
        return False
    try:
        return isfinite(value)
    except (TypeError, ValueError, OverflowError):
        return False


def _within_tolerance(observed: float, expected: float, tolerance: float) -> bool:
    """Compare decimal-like execution values without rejecting a boundary due to float noise."""
    try:
        return isclose(
            observed,
            expected,
            rel_tol=0.0,
            abs_tol=tolerance + 1e-12,
        )
    except (TypeError, ValueError, OverflowError):
        return False


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
    if not _is_finite_number(price_tolerance) or price_tolerance < 0:
        raise ValueError("price_tolerance must be finite and non-negative")
    if not _is_finite_number(volume_tolerance) or volume_tolerance < 0:
        raise ValueError("volume_tolerance must be finite and non-negative")

    reasons: list[str] = []

    intent_order_id_valid = type(intent.order_id) is str and bool(intent.order_id.strip())
    report_order_id_valid = type(report.order_id) is str and bool(report.order_id.strip())
    if not intent_order_id_valid or not report_order_id_valid:
        reasons.append("invalid order identity")
    elif report.order_id != intent.order_id:
        reasons.append("order identity mismatch")

    intent_symbol_valid = type(intent.symbol) is str and bool(intent.symbol.strip())
    report_symbol_valid = type(report.symbol) is str and bool(report.symbol.strip())
    if not intent_symbol_valid or not report_symbol_valid:
        reasons.append("invalid symbol")
    elif report.symbol != intent.symbol:
        reasons.append("symbol mismatch")

    if not isinstance(intent.direction, Direction) or not isinstance(report.direction, Direction):
        reasons.append("invalid direction")
    elif report.direction is not intent.direction:
        reasons.append("direction mismatch")

    if (
        not _is_finite_number(intent.volume)
        or intent.volume <= 0
        or not _is_finite_number(report.volume)
        or report.volume <= 0
    ):
        reasons.append("invalid volume")
    elif not _within_tolerance(report.volume, intent.volume, volume_tolerance):
        reasons.append("volume mismatch")

    if (
        not _is_finite_number(intent.expected_price)
        or intent.expected_price <= 0
        or not _is_finite_number(report.fill_price)
        or report.fill_price <= 0
    ):
        reasons.append("invalid execution price")
    elif not _within_tolerance(report.fill_price, intent.expected_price, price_tolerance):
        reasons.append("fill price outside tolerance")

    return ReconciliationResult(not reasons, tuple(reasons))
