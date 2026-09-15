"""Fail-closed market-data validation for SHREEK research datasets.

The validator is broker-neutral and performs no network or execution work. It
rejects malformed OHLCV sequences before they can enter backtesting/WFO.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite
from typing import Sequence

from research.breakout_retest import ResearchBar


@dataclass(frozen=True)
class MarketDataValidation:
    """Immutable validation result for a chronological research dataset."""

    bar_count: int
    first_timestamp: datetime | None
    last_timestamp: datetime | None
    duplicate_timestamps: int
    non_monotonic_pairs: int
    gaps_over_limit: int

    @property
    def valid(self) -> bool:
        return (
            self.bar_count > 0
            and self.duplicate_timestamps == 0
            and self.non_monotonic_pairs == 0
            and self.gaps_over_limit == 0
        )


def validate_market_data(
    bars: Sequence[ResearchBar],
    *,
    max_gap: timedelta | None = None,
) -> MarketDataValidation:
    """Validate OHLCV bars and chronological integrity.

    Timestamps must be timezone-aware and strictly increasing. A max-gap check
    is optional so normal market-session/weekend gaps can remain valid unless a
    caller explicitly requires a fixed sampling interval.
    """
    if max_gap is not None and (not isinstance(max_gap, timedelta) or max_gap <= timedelta(0)):
        raise ValueError("max_gap must be a positive timedelta or None")
    if not isinstance(bars, Sequence):
        raise ValueError("bars must be a sequence")

    duplicate_timestamps = 0
    non_monotonic_pairs = 0
    gaps_over_limit = 0
    previous: datetime | None = None

    for bar in bars:
        if not isinstance(bar, ResearchBar):
            raise ValueError("all bars must be ResearchBar instances")
        bar.validate()
        if not isinstance(bar.timestamp, datetime) or bar.timestamp.tzinfo is None:
            raise ValueError("bar timestamps must be timezone-aware datetimes")
        if not isfinite(float(bar.timestamp.timestamp())):
            raise ValueError("bar timestamp must be finite")
        if previous is not None:
            delta = bar.timestamp - previous
            if delta == timedelta(0):
                duplicate_timestamps += 1
            if delta <= timedelta(0):
                non_monotonic_pairs += 1
            if max_gap is not None and delta > max_gap:
                gaps_over_limit += 1
        previous = bar.timestamp

    first = bars[0].timestamp if bars else None
    last = bars[-1].timestamp if bars else None
    result = MarketDataValidation(
        bar_count=len(bars),
        first_timestamp=first,
        last_timestamp=last,
        duplicate_timestamps=duplicate_timestamps,
        non_monotonic_pairs=non_monotonic_pairs,
        gaps_over_limit=gaps_over_limit,
    )
    if not result.valid:
        raise ValueError(
            "market data failed chronological validation: "
            f"duplicates={result.duplicate_timestamps}, "
            f"non_monotonic={result.non_monotonic_pairs}, "
            f"gaps_over_limit={result.gaps_over_limit}"
        )
    return result
