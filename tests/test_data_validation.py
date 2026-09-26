from datetime import datetime, timedelta, timezone, tzinfo

import pytest

from research.breakout_retest import ResearchBar
from research.data_validation import validate_market_data


def _bars():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return (
        ResearchBar(start, 100.0, 101.0, 99.0, 100.5, 10.0),
        ResearchBar(start + timedelta(minutes=5), 100.5, 101.5, 100.0, 101.0, 12.0),
    )


def test_valid_data_returns_integrity_evidence():
    result = validate_market_data(_bars(), max_gap=timedelta(minutes=5))
    assert result.valid is True
    assert result.bar_count == 2
    assert result.duplicate_timestamps == 0
    assert result.non_monotonic_pairs == 0
    assert result.gaps_over_limit == 0


def test_rejects_duplicate_timestamps():
    bars = list(_bars())
    bars[1] = ResearchBar(bars[0].timestamp, 100.5, 101.5, 100.0, 101.0, 12.0)
    with pytest.raises(ValueError, match="chronological validation"):
        validate_market_data(bars)


def test_rejects_non_monotonic_timestamps():
    bars = list(_bars())
    bars[1] = ResearchBar(bars[0].timestamp - timedelta(minutes=5), 100.5, 101.5, 100.0, 101.0, 12.0)
    with pytest.raises(ValueError, match="chronological validation"):
        validate_market_data(bars)


def test_optional_gap_limit_is_fail_closed():
    bars = list(_bars())
    bars[1] = ResearchBar(bars[0].timestamp + timedelta(minutes=10), 100.5, 101.5, 100.0, 101.0, 12.0)
    with pytest.raises(ValueError, match="gaps_over_limit=1"):
        validate_market_data(bars, max_gap=timedelta(minutes=5))


def test_rejects_naive_timestamps():
    bars = list(_bars())
    bars[0] = ResearchBar(datetime(2026, 1, 1), 100.0, 101.0, 99.0, 100.5, 10.0)
    with pytest.raises(ValueError, match="timezone-aware"):
        validate_market_data(bars)


def test_empty_dataset_is_rejected():
    with pytest.raises(ValueError, match="chronological validation"):
        validate_market_data([])


class _PseudoAwareTimezone(tzinfo):
    def utcoffset(self, dt):
        return None

    def dst(self, dt):
        return None


def test_rejects_timezone_object_without_utc_offset():
    bars = list(_bars())
    pseudo = datetime(2026, 1, 1, tzinfo=_PseudoAwareTimezone())
    bars[0] = ResearchBar(pseudo, 100.0, 101.0, 99.0, 100.5, 10.0)
    with pytest.raises(ValueError, match="timezone-aware"):
        validate_market_data(bars)
