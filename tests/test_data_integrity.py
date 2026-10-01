from datetime import datetime, timedelta, timezone

import pytest

from market.data_integrity import require_valid_bars, validate_bars


UTC = timezone.utc


def _bars():
    start = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
    return [
        {"timestamp": start, "open": 1.0, "high": 1.2, "low": 0.9, "close": 1.1},
        {"timestamp": start + timedelta(minutes=5), "open": 1.1, "high": 1.3, "low": 1.0, "close": 1.2},
    ]


def test_valid_bars_pass():
    result = validate_bars(_bars())
    assert result.valid
    assert result.checked_bars == 2


def test_duplicate_timestamp_is_rejected():
    bars = _bars()
    bars[1]["timestamp"] = bars[0]["timestamp"]
    assert not validate_bars(bars).valid


def test_out_of_order_is_rejected():
    bars = _bars()
    bars[1]["timestamp"] = bars[0]["timestamp"] - timedelta(minutes=1)
    assert not validate_bars(bars).valid


def test_invalid_geometry_is_rejected():
    bars = _bars()
    bars[1]["high"] = 0.8
    assert not validate_bars(bars).valid


def test_non_finite_ohlc_is_rejected():
    bars = _bars()
    bars[1]["close"] = float("nan")
    assert not validate_bars(bars).valid


def test_timeframe_alignment_is_rejected_when_invalid():
    bars = _bars()
    bars[1]["timestamp"] += timedelta(minutes=1)
    assert not validate_bars(bars, timeframe_minutes=5).valid


def test_naive_timestamp_is_rejected():
    bars = _bars()
    bars[1]["timestamp"] = bars[1]["timestamp"].replace(tzinfo=None)
    assert not validate_bars(bars).valid


def test_future_and_stale_data_are_rejected():
    now = datetime(2026, 9, 12, 12, 10, tzinfo=UTC)
    bars = _bars()
    assert validate_bars(bars, now=now, max_staleness_minutes=10).valid
    assert not validate_bars(bars, now=now - timedelta(minutes=10)).valid
    assert not validate_bars(bars, now=now + timedelta(hours=1), max_staleness_minutes=10).valid


def test_require_valid_fails_closed():
    with pytest.raises(ValueError, match="market-data integrity failure"):
        require_valid_bars([])
