from datetime import datetime, time

from core.trading_session import SessionWindow, TradingSessionPolicy


def test_session_window_supports_overnight_window():
    window = SessionWindow("overnight", time(22), time(2))
    assert window.contains(datetime(2026, 9, 11, 23, 30))
    assert window.contains(datetime(2026, 9, 12, 1, 30))
    assert not window.contains(datetime(2026, 9, 12, 12, 0))


def test_policy_blocks_weekends():
    policy = TradingSessionPolicy(windows=(SessionWindow("day", time(8), time(18)),))
    assert not policy.allowed(datetime(2026, 9, 12, 10))
    assert policy.allowed(datetime(2026, 9, 11, 10))


def test_max_holding_period():
    policy = TradingSessionPolicy(max_holding_minutes=60)
    entry = datetime(2026, 9, 11, 10)
    assert not policy.holding_expired(entry, datetime(2026, 9, 11, 10, 59))
    assert policy.holding_expired(entry, datetime(2026, 9, 11, 11))
