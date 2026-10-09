from dataclasses import replace
from decimal import Decimal

import pytest

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


@pytest.mark.parametrize(
    "field",
    ("max_abs_slippage", "max_spread", "max_latency_ms"),
)
@pytest.mark.parametrize(
    "invalid_value",
    (True, False, "0.2", None, Decimal("0.2")),
    ids=("true", "false", "numeric-text", "none", "decimal"),
)
def test_policy_rejects_coercible_or_non_builtin_numbers(field, invalid_value):
    values = {
        "max_abs_slippage": 0.2,
        "max_spread": 0.5,
        "max_latency_ms": 250.0,
    }
    values[field] = invalid_value

    with pytest.raises(ValueError, match="numbers"):
        ExecutionQualityPolicy(**values).validate()


def test_policy_rejects_integer_too_large_for_finite_float_validation():
    policy = ExecutionQualityPolicy(10**10_000, 0.5, 250.0)

    with pytest.raises(ValueError, match="finite"):
        policy.validate()


def test_policy_accepts_plain_non_negative_ints_and_floats():
    ExecutionQualityPolicy(0, 1, 250.0).validate()
