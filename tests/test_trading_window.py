from datetime import datetime, time

import pytest

from core.trading_window import SessionWindow, TradingWindowPolicy


def test_weekday_session_allows_only_configured_window():
    policy = TradingWindowPolicy((SessionWindow("NY", time(13), time(17)),))
    assert policy.is_open(datetime(2026, 9, 11, 14))
    assert not policy.is_open(datetime(2026, 9, 11, 18))
    assert not policy.is_open(datetime(2026, 9, 12, 14))


def test_overnight_session_is_causal_and_weekday_scoped():
    policy = TradingWindowPolicy((SessionWindow("overnight", time(22), time(2)),))
    assert policy.is_open(datetime(2026, 9, 10, 23))
    assert policy.is_open(datetime(2026, 9, 11, 1))
    assert not policy.is_open(datetime(2026, 9, 11, 3))


def test_holding_expiry_is_exact():
    policy = TradingWindowPolicy(max_holding_minutes=30)
    entry = datetime(2026, 9, 11, 14)
    assert not policy.holding_expired(entry, datetime(2026, 9, 11, 14, 29))
    assert policy.holding_expired(entry, datetime(2026, 9, 11, 14, 30))


def test_holding_time_cannot_run_backwards():
    policy = TradingWindowPolicy(max_holding_minutes=30)
    with pytest.raises(ValueError):
        policy.holding_expired(datetime(2026, 9, 11, 14, 30), datetime(2026, 9, 11, 14))


def test_invalid_holding_policy_is_rejected():
    with pytest.raises(ValueError):
        TradingWindowPolicy(max_holding_minutes=0).validate()
