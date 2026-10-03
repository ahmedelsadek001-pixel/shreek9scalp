import pytest
from dataclasses import replace

from core.enums import Direction
from execution.quality_gate import ExecutionQualityPolicy, evaluate_quality
from execution.reconciliation import ExecutionReport, OrderIntent


POLICY = ExecutionQualityPolicy(
    max_abs_slippage=0.2,
    max_spread=0.5,
    max_latency_ms=250.0,
)


def _execution():
    intent = OrderIntent("A", "XAUUSD", Direction.BUY, 0.03, 100.0)
    report = ExecutionReport("A", "XAUUSD", Direction.BUY, 0.03, 100.1)
    return intent, report


def test_safe_execution_is_allowed():
    intent, report = _execution()
    result = evaluate_quality(
        POLICY,
        intent=intent,
        report=report,
        spread=0.3,
        latency_ms=120.0,
    )
    assert result.allowed is True
    assert result.reasons == ()


def test_bad_execution_is_blocked():
    intent, report = _execution()
    result = evaluate_quality(
        POLICY,
        intent=intent,
        report=replace(report, fill_price=100.3),
        spread=0.7,
        latency_ms=400.0,
    )
    assert result.allowed is False
    assert result.reasons == (
        "slippage outside limit",
        "spread outside limit",
        "latency outside limit",
    )


def test_invalid_observations_fail_closed():
    intent, report = _execution()
    result = evaluate_quality(
        POLICY,
        intent=replace(intent, expected_price=float("nan")),
        report=report,
        spread=0.1,
        latency_ms=50.0,
    )
    assert result.allowed is False
    assert result.reasons == ("execution observations must be finite",)


def test_invalid_policy_rejected():
    intent, report = _execution()
    with pytest.raises(ValueError):
        evaluate_quality(
            ExecutionQualityPolicy(-0.1, 0.5, 250.0),
            intent=intent,
            report=report,
            spread=0.1,
            latency_ms=10.0,
        )
