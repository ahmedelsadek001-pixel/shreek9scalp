import pytest

from execution.quality_gate import ExecutionQualityPolicy, evaluate_quality


POLICY = ExecutionQualityPolicy(
    max_abs_slippage=0.2,
    max_spread=0.5,
    max_latency_ms=250.0,
)


def test_safe_execution_is_allowed():
    result = evaluate_quality(
        POLICY,
        expected_price=100.0,
        fill_price=100.1,
        spread=0.3,
        latency_ms=120.0,
    )
    assert result.allowed is True
    assert result.reasons == ()


def test_bad_execution_is_blocked():
    result = evaluate_quality(
        POLICY,
        expected_price=100.0,
        fill_price=100.3,
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
    result = evaluate_quality(
        POLICY,
        expected_price=float("nan"),
        fill_price=100.0,
        spread=0.1,
        latency_ms=50.0,
    )
    assert result.allowed is False
    assert result.reasons == ("execution observations must be finite",)


def test_invalid_policy_rejected():
    with pytest.raises(ValueError):
        evaluate_quality(
            ExecutionQualityPolicy(-0.1, 0.5, 250.0),
            expected_price=100.0,
            fill_price=100.0,
            spread=0.1,
            latency_ms=10.0,
        )
