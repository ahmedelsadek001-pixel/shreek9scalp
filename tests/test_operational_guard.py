from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from execution.operational_guard import (
    OperationalPolicy,
    OperationalSnapshot,
    evaluate_operational_readiness,
)


def snapshot(age=1.0, heartbeat_age=1.0, *, connected=True, trading_enabled=True):
    now = datetime.now(timezone.utc)
    return OperationalSnapshot(
        observed_at=now,
        quote_time=now - timedelta(seconds=age),
        heartbeat_at=now - timedelta(seconds=heartbeat_age) if heartbeat_age is not None else None,
        connected=connected,
        trading_enabled=trading_enabled,
    )


def test_fresh_environment_is_ready():
    allowed, reasons = evaluate_operational_readiness(OperationalPolicy(), snapshot())
    assert allowed is True
    assert reasons == ()


def test_stale_quote_blocks():
    allowed, reasons = evaluate_operational_readiness(
        OperationalPolicy(max_quote_age_seconds=2.0), snapshot(age=3.0)
    )
    assert allowed is False
    assert "quote is stale" in reasons


def test_missing_heartbeat_blocks():
    allowed, reasons = evaluate_operational_readiness(OperationalPolicy(), snapshot(heartbeat_age=None))
    assert allowed is False
    assert "heartbeat missing" in reasons


def test_stale_heartbeat_blocks():
    allowed, reasons = evaluate_operational_readiness(
        OperationalPolicy(max_quote_age_seconds=5.0), snapshot(heartbeat_age=6.0)
    )
    assert allowed is False
    assert "heartbeat is stale" in reasons


def test_future_heartbeat_blocks():
    now = datetime.now(timezone.utc)
    environment = OperationalSnapshot(
        observed_at=now,
        quote_time=now - timedelta(seconds=1),
        heartbeat_at=now + timedelta(seconds=3),
        connected=True,
        trading_enabled=True,
    )
    allowed, reasons = evaluate_operational_readiness(OperationalPolicy(), environment)
    assert allowed is False
    assert "heartbeat timestamp is ahead of observation" in reasons


def test_disconnected_environment_blocks():
    allowed, reasons = evaluate_operational_readiness(OperationalPolicy(), snapshot(connected=False))
    assert allowed is False
    assert "environment disconnected" in reasons


def test_non_boolean_operational_state_blocks():
    allowed, reasons = evaluate_operational_readiness(
        OperationalPolicy(), snapshot(connected=1)
    )
    assert allowed is False
    assert "connected and trading_enabled must be boolean" in reasons


def test_invalid_policy_rejected():
    with pytest.raises(ValueError):
        evaluate_operational_readiness(OperationalPolicy(max_quote_age_seconds=-1), snapshot())


def test_malformed_snapshot_fails_closed():
    with pytest.raises(TypeError, match="snapshot must be OperationalSnapshot"):
        evaluate_operational_readiness(OperationalPolicy(), object())


@pytest.mark.parametrize(
    "field",
    ("max_quote_age_seconds", "max_clock_skew_seconds"),
)
@pytest.mark.parametrize(
    "invalid_value",
    (True, False, "2.0", None, Decimal("2.0")),
    ids=("true", "false", "numeric-text", "none", "decimal"),
)
def test_policy_rejects_coercible_or_non_builtin_timing_limits(
    field, invalid_value,
):
    values = {
        "max_quote_age_seconds": 5.0,
        "max_clock_skew_seconds": 2.0,
    }
    values[field] = invalid_value

    with pytest.raises(ValueError, match="numbers"):
        OperationalPolicy(**values).validate()


def test_policy_rejects_integer_too_large_for_finite_float_validation():
    policy = OperationalPolicy(max_quote_age_seconds=10**10_000)

    with pytest.raises(ValueError, match="finite"):
        policy.validate()


def test_policy_accepts_plain_non_negative_ints_and_floats():
    OperationalPolicy(
        max_quote_age_seconds=5,
        max_clock_skew_seconds=2.0,
    ).validate()
