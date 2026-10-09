"""Fail-closed execution quality gate for SHREEK V5.3.

This layer evaluates an observed execution snapshot against explicit limits.
It has no broker transport authority and never sends or modifies orders.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite

from execution.decision_provenance import IssuedDecisionRegistry
from execution.reconciliation import (
    ExecutionReport,
    OrderIntent,
    fingerprint_execution_report,
    fingerprint_order_intent,
)


_QUALITY_CAPABILITY = object()
_ISSUED_QUALITY_DECISIONS = IssuedDecisionRegistry()


@dataclass(frozen=True)
class ExecutionQualityPolicy:
    max_abs_slippage: float
    max_spread: float
    max_latency_ms: float

    def validate(self) -> None:
        values = (self.max_abs_slippage, self.max_spread, self.max_latency_ms)
        if any(type(value) not in (int, float) for value in values):
            raise ValueError(
                "execution quality limits must be built-in int or float numbers")
        try:
            finite = all(isfinite(value) for value in values)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(
                "execution quality limits must be finite") from exc
        if not finite:
            raise ValueError("execution quality limits must be finite")
        if any(value < 0 for value in values):
            raise ValueError("execution quality limits must be non-negative")


@dataclass(frozen=True)
class ExecutionQualityDecision:
    allowed: bool
    reasons: tuple[str, ...]
    intent_fingerprint: str | None = None
    report_fingerprint: str | None = None
    _capability: object | None = field(default=None, repr=False, compare=False)


def _decision_state(decision: ExecutionQualityDecision) -> tuple[object, ...]:
    return (
        decision.allowed,
        decision.reasons,
        decision.intent_fingerprint,
        decision.report_fingerprint,
    )


def _issue_decision(
    allowed: bool,
    reasons: tuple[str, ...],
    intent_fingerprint: str | None,
    report_fingerprint: str | None,
) -> ExecutionQualityDecision:
    decision = ExecutionQualityDecision(
        allowed,
        reasons,
        intent_fingerprint,
        report_fingerprint,
        _QUALITY_CAPABILITY,
    )
    _ISSUED_QUALITY_DECISIONS.issue(decision, _decision_state(decision))
    return decision


def is_quality_issued(decision: ExecutionQualityDecision) -> bool:
    """Reject caller-created, copied, or edited quality decisions."""
    return (
        isinstance(decision, ExecutionQualityDecision)
        and decision._capability is _QUALITY_CAPABILITY
        and _ISSUED_QUALITY_DECISIONS.is_issued(
            decision, _decision_state(decision))
    )


def _is_finite_number(value: object) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return isfinite(value)
    except (TypeError, ValueError, OverflowError):
        return False


def evaluate_quality(
    policy: ExecutionQualityPolicy,
    *,
    intent: OrderIntent,
    report: ExecutionReport,
    spread: float,
    latency_ms: float,
) -> ExecutionQualityDecision:
    """Evaluate execution observations against policy limits; fail closed."""
    policy.validate()
    if not isinstance(intent, OrderIntent) or not isinstance(report, ExecutionReport):
        raise TypeError("intent and report must use the reconciliation models")
    expected_price = intent.expected_price
    fill_price = report.fill_price
    values = (expected_price, fill_price, spread, latency_ms)
    if not all(_is_finite_number(value) for value in values):
        return _issue_decision(
            False, ("execution observations must be finite",), None, None)
    if expected_price <= 0 or fill_price <= 0:
        return _issue_decision(
            False, ("execution prices must be positive",), None, None)
    if spread < 0 or latency_ms < 0:
        return _issue_decision(
            False, ("spread and latency must be non-negative",), None, None)

    try:
        intent_fingerprint = fingerprint_order_intent(intent)
        report_fingerprint = fingerprint_execution_report(report)
    except (TypeError, ValueError, AttributeError, OverflowError):
        return _issue_decision(
            False, ("execution binding is invalid",), None, None)

    reasons: list[str] = []
    slippage = abs(fill_price - expected_price)
    if slippage > policy.max_abs_slippage:
        reasons.append("slippage outside limit")
    if spread > policy.max_spread:
        reasons.append("spread outside limit")
    if latency_ms > policy.max_latency_ms:
        reasons.append("latency outside limit")
    return _issue_decision(
        not reasons,
        tuple(reasons),
        intent_fingerprint,
        report_fingerprint,
    )
