from datetime import timezone
from io import StringIO

import pytest

from research.csv_adapter import load_ohlcv_csv


VALID = """timestamp,open,high,low,close,volume
2026-01-01T10:00:00Z,100,101,99,100.5,10
2026-01-01T10:05:00+00:00,100.5,101.5,100,101,12
"""

NAIVE = """timestamp,open,high,low,close,volume
2026-01-01T10:00:00,100,101,99,100.5,10
2026-01-01T10:05:00,100.5,101.5,100,101,12
"""

OFFSET_AWARE = """timestamp,open,high,low,close,volume
2026-01-01T13:00:00+03:00,100,101,99,100.5,10
2026-01-01T10:05:00Z,100.5,101.5,100,101,12
"""

MT5_AWARE = """timestamp,open,high,low,close,volume
2016.01.04T01:00:00+03:00,1064.88,1065.87,1061.66,1063.05,2550
2016.01.04T02:00:00+03:00,1063.01,1064.67,1062.65,1064.43,3773
"""


def test_loads_valid_csv_and_returns_validation_evidence():
    bars, result = load_ohlcv_csv(VALID)
    assert len(bars) == 2
    assert result.valid is True
    assert result.bar_count == 2
    assert bars[0].timestamp.tzinfo is not None


def test_accepts_text_stream():
    bars, _ = load_ohlcv_csv(StringIO(VALID))
    assert len(bars) == 2


def test_rejects_missing_header():
    with pytest.raises(ValueError, match="header"):
        load_ohlcv_csv("100,101,99,100,10\n")


def test_rejects_wrong_header():
    with pytest.raises(ValueError, match="header must be exactly"):
        load_ohlcv_csv(VALID.replace("volume", "tick_volume"))


def test_rejects_malformed_numeric_field():
    bad = VALID.replace(",101,99,", ",oops,99,", 1)
    with pytest.raises(ValueError, match="invalid high"):
        load_ohlcv_csv(bad)


def test_rejects_naive_timestamp_without_explicit_timezone():
    with pytest.raises(ValueError, match="timezone-aware"):
        load_ohlcv_csv(NAIVE)


def test_accepts_naive_timestamp_only_with_explicit_timezone():
    bars, result = load_ohlcv_csv(NAIVE, assume_timezone=timezone.utc)
    assert result.valid is True
    assert all(bar.timestamp.tzinfo is not None for bar in bars)
    assert bars[0].timestamp.utcoffset().total_seconds() == 0


def test_orders_rows_by_absolute_instant_across_offsets():
    bars, result = load_ohlcv_csv(OFFSET_AWARE)
    assert result.valid is True
    assert bars[0].timestamp.utcoffset().total_seconds() == 3 * 3600
    assert bars[0].timestamp.astimezone(timezone.utc).hour == 10
    assert bars[1].timestamp.hour == 10


def test_accepts_strict_mt5_dotted_timestamp_with_explicit_offset():
    bars, result = load_ohlcv_csv(MT5_AWARE)
    assert result.valid is True
    assert bars[0].timestamp.year == 2016
    assert bars[0].timestamp.utcoffset().total_seconds() == 3 * 3600


def test_rejects_non_monotonic_rows():
    bad = VALID.replace(
        "2026-01-01T10:05:00+00:00", "2026-01-01T09:55:00+00:00"
    )
    with pytest.raises(ValueError, match="chronological validation"):
        load_ohlcv_csv(bad)


def test_rejects_empty_dataset():
    with pytest.raises(ValueError, match="chronological validation"):
        load_ohlcv_csv("timestamp,open,high,low,close,volume\n")


def test_rejects_extra_columns():
    bad = VALID.replace("volume\n", "volume,spread\n")
    with pytest.raises(ValueError, match="header must be exactly"):
        load_ohlcv_csv(bad)
