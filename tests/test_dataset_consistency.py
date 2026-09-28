from datetime import datetime, timedelta, timezone

import pytest

from research.breakout_retest import ResearchBar
from research.dataset_consistency import compare_overlapping_datasets


def bars(closes, *, start=None):
    start = start or datetime(2026, 1, 1, tzinfo=timezone.utc)
    return tuple(
        ResearchBar(start + timedelta(minutes=15 * i), price, price + 1, price - 1, price, 10)
        for i, price in enumerate(closes)
    )


def test_equivalent_prices_with_different_offsets_are_compared_as_same_instants():
    left = bars([100, 101, 102])
    plus_three = timezone(timedelta(hours=3))
    shifted = bars([100, 101, 102], start=datetime(2026, 1, 1, 3, tzinfo=plus_three))
    result = compare_overlapping_datasets(
        left, shifted, minimum_common_timestamps=3
    )
    assert result.consistent is True
    assert result.common_timestamps == 3
    assert result.max_difference_pct == 0.0


def test_large_price_disagreement_fails_even_when_both_series_are_valid():
    result = compare_overlapping_datasets(
        bars([3200, 3210, 3220]),
        bars([2450, 2460, 2470]),
        minimum_common_timestamps=3,
    )
    assert result.consistent is False
    assert result.common_timestamps == 3
    assert result.median_difference_pct > 20.0


def test_large_finite_prices_cannot_overflow_into_zero_disagreement():
    result = compare_overlapping_datasets(
        bars([1e308] * 3),
        bars([1.1e308] * 3),
        minimum_common_timestamps=3,
    )
    assert result.consistent is False
    assert result.median_difference_pct == pytest.approx(9.5238095238)
    assert result.p95_difference_pct == pytest.approx(9.5238095238)


def test_opposite_finite_extreme_prices_stay_bounded():
    result = compare_overlapping_datasets(
        bars([1e308] * 3),
        bars([-1e308] * 3),
        minimum_common_timestamps=3,
    )
    assert result.consistent is False
    assert result.max_difference_pct == pytest.approx(200.0)


def test_same_prices_at_common_times_do_not_hide_different_bar_intervals():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    fifteen_minute = bars([100, 101, 102])
    five_minute = tuple(
        ResearchBar(
            start + timedelta(minutes=5 * index),
            close,
            close + 1,
            close - 1,
            close,
            10,
        )
        for index, close in enumerate([100, 99, 99, 101, 99, 99, 102])
    )
    result = compare_overlapping_datasets(
        fifteen_minute, five_minute, minimum_common_timestamps=3
    )
    assert result.common_timestamps == 3
    assert result.median_difference_pct == 0.0
    assert result.left_interval_seconds == 900
    assert result.right_interval_seconds == 300
    assert result.consistent is False


def test_insufficient_overlap_fails_closed():
    result = compare_overlapping_datasets(
        bars([100, 101, 102]),
        bars([100, 101, 102]),
        minimum_common_timestamps=4,
    )
    assert result.consistent is False
    assert result.common_timestamps == 3


def test_invalid_or_duplicate_timestamps_are_rejected_before_comparison():
    left = bars([100, 101, 102])
    duplicate = (left[0], left[0], left[2])
    with pytest.raises(ValueError, match="chronological validation"):
        compare_overlapping_datasets(left, duplicate, minimum_common_timestamps=1)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"minimum_common_timestamps": 0},
        {"max_median_difference_pct": -1},
        {"max_p95_difference_pct": float("nan")},
        {"max_p95_difference_pct": True},
    ],
)
def test_invalid_consistency_policy_is_rejected(kwargs):
    with pytest.raises(ValueError):
        compare_overlapping_datasets(bars([100, 101]), bars([100, 101]), **kwargs)
