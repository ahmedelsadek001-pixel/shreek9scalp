from dataclasses import replace

import pytest

from core.enums import Direction
from execution.post_trade_guard import evaluate_post_trade
from execution.quality_gate import (
    ExecutionQualityDecision,
    ExecutionQualityPolicy,
    evaluate_quality,
)
from execution.reconciliation import ExecutionReport, OrderIntent, reconcile_execution


POLICY = ExecutionQualityPolicy(0.2, 0.5, 250.0)


def _intent(**changes):
    values = dict(
        order_id="TARGET", symbol="XAUUSD", direction=Direction.BUY,
        volume=0.03, expected_price=2500.0,
    )
    values.update(changes)
    return OrderIntent(**values)


def _report(intent):
    return ExecutionReport(
        intent.order_id, intent.symbol, intent.direction,
        intent.volume, intent.expected_price,
    )


def _quality(intent, report, *, spread=0.1, latency_ms=10.0):
    return evaluate_quality(
        POLICY,
        intent=intent,
        report=report,
        spread=spread,
        latency_ms=latency_ms,
    )


def _post_trade(intent, report, quality):
    return evaluate_post_trade(
        reconciliation=reconcile_execution(intent, report),
        quality=quality,
    )


def test_forged_positive_quality_decision_cannot_pass_post_trade_gate():
    intent = _intent()
    report = _report(intent)

    decision = _post_trade(intent, report, ExecutionQualityDecision(True, ()))

    assert decision.accepted is False
    assert "execution quality decision not issued by quality gate" in decision.reasons


@pytest.mark.parametrize(
    "changes",
    [
        {"order_id": "OTHER"},
        {"symbol": "XAGUSD"},
        {"direction": Direction.SELL},
        {"volume": 0.04},
        {"expected_price": 2500.1},
    ],
)
def test_quality_for_another_intent_cannot_validate_target(changes):
    target = _intent()
    target_report = _report(target)
    other = _intent(**changes)

    decision = _post_trade(
        target,
        target_report,
        _quality(other, target_report),
    )

    assert decision.accepted is False
    assert "execution quality decision does not match reconciliation" in decision.reasons


@pytest.mark.parametrize(
    "changes",
    [
        {"order_id": "OTHER"},
        {"symbol": "XAGUSD"},
        {"direction": Direction.SELL},
        {"volume": 0.04},
        {"fill_price": 2500.1},
    ],
)
def test_quality_for_another_report_cannot_validate_target(changes):
    target = _intent()
    target_report = _report(target)
    other_report = replace(target_report, **changes)

    decision = _post_trade(
        target,
        target_report,
        _quality(target, other_report),
    )

    assert decision.accepted is False
    assert "execution quality decision does not match reconciliation" in decision.reasons


def test_copied_quality_decision_cannot_pass_post_trade_gate():
    intent = _intent()
    report = _report(intent)
    copied = replace(_quality(intent, report))

    decision = _post_trade(intent, report, copied)

    assert decision.accepted is False
    assert "execution quality decision not issued by quality gate" in decision.reasons


def test_edited_quality_decision_cannot_pass_post_trade_gate():
    intent = _intent()
    report = _report(intent)
    edited = _quality(intent, report)
    object.__setattr__(edited, "intent_fingerprint", "0" * 64)

    decision = _post_trade(intent, report, edited)

    assert decision.accepted is False
    assert "execution quality decision not issued by quality gate" in decision.reasons


def test_issued_quality_for_same_execution_can_pass_post_trade_gate():
    intent = _intent()
    report = _report(intent)

    decision = _post_trade(intent, report, _quality(intent, report))

    assert decision.accepted is True
    assert decision.reasons == ()


def test_issued_quality_rejection_for_same_execution_remains_blocked():
    intent = _intent()
    report = _report(intent)

    decision = _post_trade(
        intent,
        report,
        _quality(intent, report, latency_ms=300.0),
    )

    assert decision.accepted is False
    assert "quality: latency outside limit" in decision.reasons
