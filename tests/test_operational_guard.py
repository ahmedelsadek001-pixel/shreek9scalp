from datetime import datetime, timedelta, timezone

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
