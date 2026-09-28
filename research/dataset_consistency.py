"""Cross-check overlapping OHLCV datasets before empirical research."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import timezone
from hashlib import sha256
from math import ceil, isfinite
from statistics import median
from typing import Sequence

from research.breakout_retest import ResearchBar
from research.data_validation import validate_market_data


@dataclass(frozen=True)
class DatasetConsistency:
    """Exact-timestamp close-price agreement for two validated datasets."""

    common_timestamps: int
    median_difference_pct: float | None
    p95_difference_pct: float | None
    max_difference_pct: float | None
    left_dataset_sha256: str
    right_dataset_sha256: str
    left_interval_seconds: float | None
    right_interval_seconds: float | None
    allowed_median_pct: float
    allowed_p95_pct: float
    minimum_common_timestamps: int

    def validate(self) -> None:
        if type(self.common_timestamps) is not int or self.common_timestamps < 0:
            raise ValueError("common_timestamps must be a non-negative integer")
        if type(self.minimum_common_timestamps) is not int or self.minimum_common_timestamps < 1:
            raise ValueError("minimum_common_timestamps must be a positive integer")
        for digest in (self.left_dataset_sha256, self.right_dataset_sha256):
            if not isinstance(digest, str) or len(digest) != 64 or any(
                char not in "0123456789abcdef" for char in digest
            ):
                raise ValueError("dataset consistency fingerprints must be SHA-256 digests")
        for interval in (self.left_interval_seconds, self.right_interval_seconds):
            if interval is not None and (
                isinstance(interval, bool)
                or not isinstance(interval, (int, float))
                or not isfinite(float(interval))
                or interval <= 0
            ):
                raise ValueError("dataset intervals must be finite positive seconds")
        for name, value in (
            ("allowed_median_pct", self.allowed_median_pct),
            ("allowed_p95_pct", self.allowed_p95_pct),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        metrics = (self.median_difference_pct, self.p95_difference_pct, self.max_difference_pct)
        if self.common_timestamps == 0 and any(value is not None for value in metrics):
            raise ValueError("price difference metrics require common timestamps")
        if self.common_timestamps > 0 and any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(float(value))
            or value < 0
            for value in metrics
        ):
            raise ValueError("price difference metrics must be finite and non-negative")
        if self.common_timestamps > 0 and not (
            self.median_difference_pct <= self.p95_difference_pct <= self.max_difference_pct
        ):
            raise ValueError("price difference summary ordering is invalid")

    @property
    def consistent(self) -> bool:
        return (
            self.left_interval_seconds is not None
            and self.left_interval_seconds == self.right_interval_seconds
            and self.common_timestamps >= self.minimum_common_timestamps
            and self.median_difference_pct is not None
            and self.p95_difference_pct is not None
            and self.median_difference_pct <= self.allowed_median_pct
            and self.p95_difference_pct <= self.allowed_p95_pct
        )


def compare_overlapping_datasets(
    left: Sequence[ResearchBar],
    right: Sequence[ResearchBar],
    *,
    minimum_common_timestamps: int = 100,
    max_median_difference_pct: float = 0.5,
    max_p95_difference_pct: float = 1.0,
) -> DatasetConsistency:
    """Fail closed when aligned close prices materially disagree.

    This is a source-consistency diagnostic, not proof that either source is
    correct. Only timestamps present in both validated datasets are compared.
    Percent difference uses the mean magnitude of each close as denominator.
    """
    if type(minimum_common_timestamps) is not int or minimum_common_timestamps < 1:
        raise ValueError("minimum_common_timestamps must be a positive integer")
    for name, value in (
        ("max_median_difference_pct", max_median_difference_pct),
        ("max_p95_difference_pct", max_p95_difference_pct),
    ):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)) or value < 0:
            raise ValueError(f"{name} must be a finite non-negative number")
    validate_market_data(left)
    validate_market_data(right)

    def fingerprint(dataset: Sequence[ResearchBar]) -> str:
        payload = ["schema=1\n"]
        for bar in dataset:
            payload.append(
                f"{bar.timestamp.isoformat()}|{bar.open:.17g}|{bar.high:.17g}|"
                f"{bar.low:.17g}|{bar.close:.17g}|{bar.volume:.17g}\n"
            )
        return sha256("".join(payload).encode("utf-8")).hexdigest()

    def nominal_interval(dataset: Sequence[ResearchBar]) -> float | None:
        deltas = [
            round(
                (current.timestamp.astimezone(timezone.utc)
                 - previous.timestamp.astimezone(timezone.utc)).total_seconds(),
                6,
            )
            for previous, current in zip(dataset, dataset[1:])
        ]
        if not deltas:
            return None
        counts = Counter(deltas)
        highest_count = max(counts.values())
        return min(value for value, count in counts.items() if count == highest_count)

    left_by_time = {bar.timestamp.astimezone(timezone.utc): bar.close for bar in left}
    right_by_time = {bar.timestamp.astimezone(timezone.utc): bar.close for bar in right}
    common = sorted(set(left_by_time).intersection(right_by_time))
    differences = []
    for timestamp in common:
        a, b = left_by_time[timestamp], right_by_time[timestamp]
        scale = max(abs(a), abs(b))
        if scale == 0.0:
            difference = 0.0
        else:
            # Scale before subtraction and addition: finite close prices near
            # the float limit must not overflow into a false 0% or NaN.
            left_scaled, right_scaled = a / scale, b / scale
            difference = (
                abs(left_scaled - right_scaled)
                / ((abs(left_scaled) + abs(right_scaled)) / 2.0)
                * 100.0
            )
        differences.append(difference)

    if not differences:
        median_pct = p95_pct = max_pct = None
    else:
        ordered = sorted(differences)
        median_pct = median(ordered)
        p95_pct = ordered[max(0, ceil(0.95 * len(ordered)) - 1)]
        max_pct = ordered[-1]
    return DatasetConsistency(
        len(common),
        median_pct,
        p95_pct,
        max_pct,
        fingerprint(left),
        fingerprint(right),
        nominal_interval(left),
        nominal_interval(right),
        float(max_median_difference_pct),
        float(max_p95_difference_pct),
        minimum_common_timestamps,
    )
