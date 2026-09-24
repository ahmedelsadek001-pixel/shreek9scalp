"""Fail-closed quality audit for XAUUSD multi-timeframe research data.

The generic CSV adapter validates schema, numeric values, and chronology.  This
module adds the instrument-specific checks required before 5m/15m/1h data can
be treated as empirical XAUUSD evidence.  It has no broker or execution access.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from math import isfinite
from typing import Mapping, Sequence

from research.breakout_retest import ResearchBar
from research.data_validation import validate_market_data


EXPECTED_INTERVALS = {
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
}


@dataclass(frozen=True)
class XAUUSDQualityPolicy:
    """Acceptance thresholds for a three-year XAUUSD research bundle."""

    minimum_span: timedelta = timedelta(days=1065)
    maximum_saturday_bars: int = 0
    minimum_pair_overlap: timedelta = timedelta(days=90)
    minimum_aggregation_bars: int = 100
    minimum_aggregation_match_pct: float = 99.0
    maximum_reused_volume_prefix_pct: float = 95.0
    price_tolerance: float = 1e-9

    def validate(self) -> None:
        if not isinstance(self.minimum_span, timedelta) or self.minimum_span <= timedelta(0):
            raise ValueError("minimum_span must be a positive timedelta")
        if type(self.maximum_saturday_bars) is not int or self.maximum_saturday_bars < 0:
            raise ValueError("maximum_saturday_bars must be a non-negative integer")
        if (
            not isinstance(self.minimum_pair_overlap, timedelta)
            or self.minimum_pair_overlap < timedelta(0)
        ):
            raise ValueError("minimum_pair_overlap must be a non-negative timedelta")
        if type(self.minimum_aggregation_bars) is not int or self.minimum_aggregation_bars < 1:
            raise ValueError("minimum_aggregation_bars must be a positive integer")
        for value, name in (
            (self.minimum_aggregation_match_pct, "minimum_aggregation_match_pct"),
            (self.maximum_reused_volume_prefix_pct, "maximum_reused_volume_prefix_pct"),
        ):
            if type(value) not in (int, float) or not isfinite(value) or not 0.0 <= value <= 100.0:
                raise ValueError(f"{name} must be finite and between 0 and 100")
        if (
            type(self.price_tolerance) not in (int, float)
            or not isfinite(self.price_tolerance)
            or self.price_tolerance < 0.0
        ):
            raise ValueError("price_tolerance must be finite and non-negative")


@dataclass(frozen=True)
class DatasetQualitySummary:
    timeframe: str
    bar_count: int
    span_days: float
    saturday_bars: int
    unexpected_intervals: int


@dataclass(frozen=True)
class AggregationQuality:
    lower_timeframe: str
    higher_timeframe: str
    overlap_days: float
    compared_bars: int
    matching_bars: int
    match_pct: float


@dataclass(frozen=True)
class DatasetQualityFinding:
    code: str
    dataset: str
    detail: str


@dataclass(frozen=True)
class XAUUSDDatasetAudit:
    passed: bool
    summaries: tuple[DatasetQualitySummary, ...]
    aggregation: tuple[AggregationQuality, ...]
    findings: tuple[DatasetQualityFinding, ...]


def _unexpected_interval_count(
    bars: Sequence[ResearchBar], expected_interval: timedelta
) -> int:
    expected_seconds = int(expected_interval.total_seconds())
    count = 0
    for previous, current in zip(bars, bars[1:]):
        seconds = int((current.timestamp - previous.timestamp).total_seconds())
        if seconds < expected_seconds or seconds % expected_seconds:
            count += 1
    return count


def _bucket_start_seconds(timestamp: object, interval: timedelta) -> int:
    seconds = int(timestamp.timestamp())
    width = int(interval.total_seconds())
    return seconds - seconds % width


def _aggregation_quality(
    lower_name: str,
    higher_name: str,
    lower: Sequence[ResearchBar],
    higher: Sequence[ResearchBar],
    *,
    tolerance: float,
) -> AggregationQuality:
    lower_interval = EXPECTED_INTERVALS[lower_name]
    higher_interval = EXPECTED_INTERVALS[higher_name]
    ratio = int(higher_interval / lower_interval)
    if ratio <= 1 or higher_interval != lower_interval * ratio:
        raise ValueError("higher timeframe must be an integer multiple of lower timeframe")

    overlap_start = max(lower[0].timestamp, higher[0].timestamp)
    overlap_end = min(lower[-1].timestamp, higher[-1].timestamp)
    overlap = max(timedelta(0), overlap_end - overlap_start)

    buckets: dict[int, list[ResearchBar]] = {}
    for bar in lower:
        if overlap_start <= bar.timestamp <= overlap_end:
            key = _bucket_start_seconds(bar.timestamp, higher_interval)
            buckets.setdefault(key, []).append(bar)

    compared = 0
    matching = 0
    lower_seconds = int(lower_interval.total_seconds())
    for bar in higher:
        if not overlap_start <= bar.timestamp <= overlap_end:
            continue
        key = _bucket_start_seconds(bar.timestamp, higher_interval)
        group = buckets.get(key, ())
        if len(group) != ratio:
            continue
        timestamps = [int(item.timestamp.timestamp()) for item in group]
        if any(right - left != lower_seconds for left, right in zip(timestamps, timestamps[1:])):
            continue
        compared += 1
        expected = (group[0].open, max(item.high for item in group),
                    min(item.low for item in group), group[-1].close)
        actual = (bar.open, bar.high, bar.low, bar.close)
        if all(abs(float(left) - float(right)) <= tolerance for left, right in zip(expected, actual)):
            matching += 1

    match_pct = matching / compared * 100.0 if compared else 0.0
    return AggregationQuality(
        lower_name,
        higher_name,
        overlap.total_seconds() / 86400.0,
        compared,
        matching,
        match_pct,
    )


def _audit_series(
    name: str,
    bars: Sequence[ResearchBar],
    expected_interval: timedelta,
    policy: XAUUSDQualityPolicy,
) -> tuple[DatasetQualitySummary, tuple[DatasetQualityFinding, ...]]:
    validate_market_data(bars)
    span = bars[-1].timestamp - bars[0].timestamp
    saturday_bars = sum(bar.timestamp.weekday() == 5 for bar in bars)
    unexpected = _unexpected_interval_count(bars, expected_interval)
    summary = DatasetQualitySummary(
        name,
        len(bars),
        span.total_seconds() / 86400.0,
        saturday_bars,
        unexpected,
    )
    findings = []
    if span < policy.minimum_span:
        findings.append(
            DatasetQualityFinding(
                "insufficient_span",
                name,
                f"span {span.total_seconds() / 86400.0:.3f} days is below minimum",
            )
        )
    if saturday_bars > policy.maximum_saturday_bars:
        findings.append(
            DatasetQualityFinding(
                "saturday_market_data",
                name,
                f"found {saturday_bars} Saturday bars",
            )
        )
    if unexpected:
        findings.append(
            DatasetQualityFinding(
                "unexpected_interval",
                name,
                f"found {unexpected} intervals off the expected timeframe grid",
            )
        )
    return summary, tuple(findings)


def _audit_aggregation(
    datasets: Mapping[str, Sequence[ResearchBar]],
    policy: XAUUSDQualityPolicy,
) -> tuple[tuple[AggregationQuality, ...], tuple[DatasetQualityFinding, ...]]:
    results = []
    findings = []
    minimum_overlap_days = policy.minimum_pair_overlap.total_seconds() / 86400.0
    for lower_name, higher_name in (("5m", "15m"), ("15m", "1h"), ("5m", "1h")):
        result = _aggregation_quality(
            lower_name,
            higher_name,
            datasets[lower_name],
            datasets[higher_name],
            tolerance=float(policy.price_tolerance),
        )
        results.append(result)
        pair = f"{lower_name}/{higher_name}"
        if result.overlap_days < minimum_overlap_days:
            findings.append(
                DatasetQualityFinding(
                    "insufficient_pair_overlap",
                    pair,
                    f"overlap {result.overlap_days:.3f} days is below minimum",
                )
            )
        elif result.compared_bars < policy.minimum_aggregation_bars:
            findings.append(
                DatasetQualityFinding(
                    "insufficient_aggregation_sample",
                    pair,
                    f"only {result.compared_bars} complete higher-timeframe bars were comparable",
                )
            )
        elif result.match_pct < policy.minimum_aggregation_match_pct:
            findings.append(
                DatasetQualityFinding(
                    "cross_timeframe_ohlc_mismatch",
                    pair,
                    f"OHLC aggregation match was {result.match_pct:.3f}%",
                )
            )
    return tuple(results), tuple(findings)


def _audit_reused_volumes(
    datasets: Mapping[str, Sequence[ResearchBar]],
    policy: XAUUSDQualityPolicy,
) -> tuple[DatasetQualityFinding, ...]:
    findings = []
    names = tuple(EXPECTED_INTERVALS)
    for index, left_name in enumerate(names):
        for right_name in names[index + 1:]:
            left = datasets[left_name]
            right = datasets[right_name]
            length = min(len(left), len(right))
            if length < policy.minimum_aggregation_bars:
                continue
            equal = sum(
                float(left[position].volume) == float(right[position].volume)
                for position in range(length)
            )
            equal_pct = equal / length * 100.0
            if equal_pct > policy.maximum_reused_volume_prefix_pct:
                findings.append(
                    DatasetQualityFinding(
                        "reused_volume_sequence",
                        f"{left_name}/{right_name}",
                        f"{equal_pct:.3f}% of the {length}-bar volume prefix is identical",
                    )
                )
    return tuple(findings)


def audit_xauusd_multitimeframe(
    datasets: Mapping[str, Sequence[ResearchBar]],
    *,
    policy: XAUUSDQualityPolicy = XAUUSDQualityPolicy(),
) -> XAUUSDDatasetAudit:
    """Audit a 5m/15m/1h XAUUSD bundle before empirical research.

    The function deliberately returns a detailed failed audit for quality
    problems.  Structurally malformed bars still raise through the generic
    market-data validator.
    """
    if not isinstance(datasets, Mapping):
        raise ValueError("datasets must be a mapping")
    policy.validate()
    if set(datasets) != set(EXPECTED_INTERVALS):
        raise ValueError("datasets must contain exactly 5m, 15m and 1h")

    summaries = []
    findings = []
    for name, expected_interval in EXPECTED_INTERVALS.items():
        summary, series_findings = _audit_series(
            name, datasets[name], expected_interval, policy
        )
        summaries.append(summary)
        findings.extend(series_findings)

    aggregation, aggregation_findings = _audit_aggregation(datasets, policy)
    findings.extend(aggregation_findings)
    findings.extend(_audit_reused_volumes(datasets, policy))

    result = XAUUSDDatasetAudit(
        not findings,
        tuple(summaries),
        aggregation,
        tuple(findings),
    )
    if result.passed != (len(result.findings) == 0):
        raise RuntimeError("dataset audit state is inconsistent")
    return result


def require_xauusd_multitimeframe_quality(
    datasets: Mapping[str, Sequence[ResearchBar]],
    *,
    policy: XAUUSDQualityPolicy = XAUUSDQualityPolicy(),
) -> XAUUSDDatasetAudit:
    """Return the audit or fail closed before WFO/robustness execution."""
    result = audit_xauusd_multitimeframe(datasets, policy=policy)
    if not result.passed:
        codes = ", ".join(finding.code for finding in result.findings)
        raise ValueError("XAUUSD dataset quality gate failed: " + codes)
    return result
