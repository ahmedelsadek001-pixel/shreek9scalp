"""Fail-closed execution reconciliation for SHREEK V5.1.

The reconciler compares an immutable order intent with an observed execution
report. It never sends, modifies, or closes broker orders.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from math import isclose, isfinite

from core.enums import Direction
from execution.decision_provenance import IssuedDecisionRegistry


_RECONCILIATION_CAPABILITY = object()
_ISSUED_RECONCILIATIONS = IssuedDecisionRegistry()


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
    intent_fingerprint: str | None = None
    report_fingerprint: str | None = None
    _capability: object | None = field(default=None, repr=False, compare=False)


def _result_state(result: ReconciliationResult) -> tuple[object, ...]:
    return (
        result.matched,
        result.reasons,
        result.intent_fingerprint,
        result.report_fingerprint,
    )


def _issue_result(
    matched: bool,
    reasons: tuple[str, ...],
    intent_fingerprint: str | None,
    report_fingerprint: str | None,
) -> ReconciliationResult:
    result = ReconciliationResult(
        matched, reasons, intent_fingerprint, report_fingerprint,
        _RECONCILIATION_CAPABILITY,
    )
    _ISSUED_RECONCILIATIONS.issue(result, _result_state(result))
    return result


def is_reconciliation_issued(result: ReconciliationResult) -> bool:
    """Reject caller-created, copied, or edited reconciliation results."""
    return (
        isinstance(result, ReconciliationResult)
        and result._capability is _RECONCILIATION_CAPABILITY
        and _ISSUED_RECONCILIATIONS.is_issued(
            result, _result_state(result))
    )


def fingerprint_order_intent(intent: OrderIntent) -> str:
    """Return the ledger's canonical binding without creating an import cycle."""
    if not isinstance(intent, OrderIntent):
        raise TypeError("intent must be OrderIntent")
    from execution.idempotency import IdempotencyLedger

    return IdempotencyLedger.fingerprint_intent(intent)


def _number_ratio(value: object) -> tuple[int, int]:
    if type(value) not in (int, float):
        raise ValueError("execution report economics must be finite and positive")
    try:
        if not isfinite(value) or value <= 0:
            raise ValueError(
                "execution report economics must be finite and positive")
    except OverflowError as exc:
        raise ValueError(
            "execution report economics must be finite and positive") from exc
    return (value, 1) if type(value) is int else value.as_integer_ratio()


def fingerprint_execution_report(report: ExecutionReport) -> str:
    """Bind the exact broker-neutral execution report used by downstream gates."""
    if not isinstance(report, ExecutionReport):
        raise TypeError("report must be ExecutionReport")
    if type(report.order_id) is not str or not report.order_id.strip():
        raise ValueError("execution report identity is required")
    if type(report.symbol) is not str or not report.symbol.strip():
        raise ValueError("execution report symbol is required")
    if not isinstance(report.direction, Direction):
        raise ValueError("execution report direction must be Direction")
    payload = {
        "version": 1,
        "order_id": report.order_id.strip(),
        "symbol": report.symbol,
        "direction": report.direction.value,
        "volume": _number_ratio(report.volume),
        "fill_price": _number_ratio(report.fill_price),
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":")).encode()
    return sha256(canonical).hexdigest()


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
    intent_fingerprint = None
    report_fingerprint = None
    try:
        intent_fingerprint = fingerprint_order_intent(intent)
    except (TypeError, ValueError, AttributeError, OverflowError):
        # Malformed intent fields are reported below as a rejected result.
        pass
    try:
        report_fingerprint = fingerprint_execution_report(report)
    except (TypeError, ValueError, AttributeError, OverflowError):
        # Malformed report fields are reported below as a rejected result.
        pass

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

    if (
        not isinstance(intent.direction, Direction)
        or intent.direction not in (Direction.BUY, Direction.SELL)
        or not isinstance(report.direction, Direction)
        or report.direction not in (Direction.BUY, Direction.SELL)
    ):
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

    return _issue_result(
        not reasons, tuple(reasons), intent_fingerprint, report_fingerprint)
