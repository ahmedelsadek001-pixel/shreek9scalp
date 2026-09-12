"""Fail-closed validation for chronological OHLC market data."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite
from typing import Iterable, Mapping, Optional, Sequence


@dataclass(frozen=True)
class DataQualityResult:
    valid: bool
    reason: str = "ok"
    checked_bars: int = 0


def _value(bar: object, name: str):
    if isinstance(bar, Mapping):
        return bar.get(name)
    return getattr(bar, name, None)


def _timestamp(bar: object) -> Optional[datetime]:
    value = _value(bar, "timestamp")
    if value is None:
        value = _value(bar, "time")
    return value


def validate_bars(
    bars: Sequence[object],
    timeframe_minutes: Optional[int] = None,
    now: Optional[datetime] = None,
    max_staleness_minutes: Optional[int] = None,
) -> DataQualityResult:
    """Validate bars without sorting, repairing, deduplicating, or dropping data."""
    if not bars:
        return DataQualityResult(False, "empty market-data stream", 0)
    if timeframe_minutes is not None and (isinstance(timeframe_minutes, bool) or timeframe_minutes <= 0):
        raise ValueError("timeframe_minutes must be positive")
    if max_staleness_minutes is not None and (isinstance(max_staleness_minutes, bool) or max_staleness_minutes < 0):
        raise ValueError("max_staleness_minutes must be non-negative")
    if now is not None and (now.tzinfo is None or now.utcoffset() is None):
        raise ValueError("now must be timezone-aware")

    previous = None
    for index, bar in enumerate(bars):
        timestamp = _timestamp(bar)
        if not isinstance(timestamp, datetime) or timestamp.tzinfo is None or timestamp.utcoffset() is None:
            return DataQualityResult(False, "bar timestamp must be timezone-aware", index)
        if previous is not None and timestamp <= previous:
            reason = "duplicate timestamp" if timestamp == previous else "out-of-order timestamp"
            return DataQualityResult(False, reason, index)
        previous = timestamp

        values = [_value(bar, name) for name in ("open", "high", "low", "close")]
        if any(value is None for value in values):
            return DataQualityResult(False, "OHLC field missing", index + 1)
        try:
            open_, high, low, close = (float(value) for value in values)
        except (TypeError, ValueError):
            return DataQualityResult(False, "OHLC value is not numeric", index + 1)
        if any(not isfinite(value) or value <= 0 for value in (open_, high, low, close)):
            return DataQualityResult(False, "OHLC value is non-finite or non-positive", index + 1)
        if high < max(open_, close) or low > min(open_, close) or low > high:
            return DataQualityResult(False, "invalid OHLC geometry", index + 1)
        if timeframe_minutes is not None:
            epoch = int(timestamp.timestamp())
            if epoch % (timeframe_minutes * 60) != 0:
                return DataQualityResult(False, "timestamp is not timeframe-aligned", index + 1)

    if now is not None:
        if previous > now:
            return DataQualityResult(False, "last bar is in the future", len(bars))
        if max_staleness_minutes is not None:
            age = now - previous
            if age > timedelta(minutes=max_staleness_minutes):
                return DataQualityResult(False, "market data is stale", len(bars))
    return DataQualityResult(True, checked_bars=len(bars))


def require_valid_bars(
    bars: Sequence[object],
    timeframe_minutes: Optional[int] = None,
    now: Optional[datetime] = None,
    max_staleness_minutes: Optional[int] = None,
) -> None:
    result = validate_bars(bars, timeframe_minutes, now, max_staleness_minutes)
    if not result.valid:
        raise ValueError("market-data integrity failure: %s" % result.reason)
