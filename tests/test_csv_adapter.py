from io import StringIO

import pytest

from research.csv_adapter import load_ohlcv_csv


VALID = """timestamp,open,high,low,close,volume
2026-01-01T10:00:00Z,100,101,99,100.5,10
2026-01-01T10:05:00+00:00,100.5,101.5,100,101,12
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


def test_rejects_naive_timestamp():
    bad = VALID.replace("2026-01-01T10:00:00Z", "2026-01-01T10:00:00")
    with pytest.raises(ValueError, match="timezone-aware"):
        load_ohlcv_csv(bad)


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
