from datetime import datetime, timedelta, timezone, tzinfo

import pytest

from research.breakout_retest import ResearchBar
from research.data_provenance import DatasetProvenance, fingerprint_bars
from research.data_validation import validate_market_data


def _bars():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return (
        ResearchBar(start, 100.0, 101.0, 99.0, 100.5, 10.0),
        ResearchBar(start + timedelta(minutes=5), 100.5, 101.5, 100.0, 101.0, 12.0),
    )


def test_fingerprint_is_deterministic():
    bars = _bars()
    validation = validate_market_data(bars)
    first = fingerprint_bars(bars, validation)
    second = fingerprint_bars(bars, validation)
    assert first == second
    assert len(first.sha256) == 64
    assert first.bar_count == 2
    first.validate()


def test_fingerprint_changes_when_market_data_changes():
    bars = _bars()
    validation = validate_market_data(bars)
    baseline = fingerprint_bars(bars, validation)
    changed = list(bars)
    changed[1] = ResearchBar(
        changed[1].timestamp,
        changed[1].open,
        changed[1].high,
        changed[1].low,
        changed[1].close + 0.01,
        changed[1].volume,
    )
    changed_validation = validate_market_data(changed)
    assert fingerprint_bars(changed, changed_validation).sha256 != baseline.sha256


def test_fingerprint_requires_matching_validation():
    bars = _bars()
    validation = validate_market_data(bars)
    with pytest.raises(ValueError, match="bar_count"):
        fingerprint_bars(bars[:1], validation)


class _PseudoAwareTimezone(tzinfo):
    def utcoffset(self, dt):
        return None

    def dst(self, dt):
        return None


@pytest.mark.parametrize(
    "timestamp",
    [
        datetime(2026, 1, 1),
        datetime(2026, 1, 1, tzinfo=_PseudoAwareTimezone()),
    ],
)
def test_provenance_rejects_non_aware_timestamps(timestamp):
    provenance = DatasetProvenance(
        "1",
        "a" * 64,
        2,
        timestamp,
        datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        provenance.validate()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("sha256", None, "sha256 must be a string"),
        ("sha256", 123, "sha256 must be a string"),
        ("bar_count", True, "bar_count must be positive"),
        ("bar_count", 2.0, "bar_count must be positive"),
    ],
)
def test_provenance_rejects_ambiguous_scalar_types(field, value, message):
    provenance = DatasetProvenance(
        "1",
        "a" * 64,
        2,
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    object.__setattr__(provenance, field, value)
    with pytest.raises(ValueError, match=message):
        provenance.validate()
