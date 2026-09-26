from datetime import datetime, timedelta, timezone

import pytest

from research.breakout_retest import ResearchBar
from research.xauusd_dataset_quality import (
    XAUUSDQualityPolicy,
    audit_xauusd_multitimeframe,
    require_xauusd_multitimeframe_quality,
)


def _bars(interval, count, *, start=None, price_shift=0.0, same_volume=False):
    start = start or datetime(2026, 9, 21, tzinfo=timezone.utc)
    result = []
    for index in range(count):
        timestamp = start + interval * index
        base = 2600.0 + price_shift + index * 0.1
        volume = 100.0 if same_volume else 100.0 + index
        result.append(ResearchBar(timestamp, base, base + 0.2, base - 0.2, base + 0.1, volume))
    return tuple(result)


def _aggregate(bars, ratio):
    result = []
    for index in range(0, len(bars), ratio):
        group = bars[index:index + ratio]
        if len(group) != ratio:
            break
        result.append(
            ResearchBar(
                group[0].timestamp,
                group[0].open,
                max(bar.high for bar in group),
                min(bar.low for bar in group),
                group[-1].close,
                sum(bar.volume for bar in group),
            )
        )
    return tuple(result)


def _bundle():
    five = _bars(timedelta(minutes=5), 72)
    return {"5m": five, "15m": _aggregate(five, 3), "1h": _aggregate(five, 12)}


def _policy(**overrides):
    values = {
        "minimum_span": timedelta(hours=5),
        "minimum_pair_overlap": timedelta(hours=4),
        "minimum_aggregation_bars": 4,
    }
    values.update(overrides)
    return XAUUSDQualityPolicy(**values)


def test_consistent_multitimeframe_bundle_passes():
    result = audit_xauusd_multitimeframe(_bundle(), policy=_policy())
    assert result.passed
    assert result.findings == ()
    assert all(item.match_pct == 100.0 for item in result.aggregation)


def test_short_dataset_fails_span_gate():
    result = audit_xauusd_multitimeframe(
        _bundle(), policy=_policy(minimum_span=timedelta(days=1))
    )
    assert not result.passed
    assert {finding.code for finding in result.findings} == {"insufficient_span"}


def test_saturday_bars_fail_closed():
    saturday = datetime(2026, 9, 19, tzinfo=timezone.utc)
    five = _bars(timedelta(minutes=5), 72, start=saturday)
    datasets = {"5m": five, "15m": _aggregate(five, 3), "1h": _aggregate(five, 12)}
    result = audit_xauusd_multitimeframe(
        datasets,
        policy=_policy(minimum_span=timedelta(hours=1), minimum_pair_overlap=timedelta(0)),
    )
    assert not result.passed
    assert "saturday_market_data" in {finding.code for finding in result.findings}


def test_cross_timeframe_price_mismatch_is_rejected():
    datasets = dict(_bundle())
    higher = list(datasets["1h"])
    first = higher[0]
    higher[0] = ResearchBar(
        first.timestamp,
        first.open + 1.0,
        first.high + 1.0,
        first.low + 1.0,
        first.close + 1.0,
        first.volume,
    )
    datasets["1h"] = tuple(higher)
    result = audit_xauusd_multitimeframe(
        datasets, policy=_policy(minimum_aggregation_match_pct=99.0)
    )
    assert not result.passed
    assert "cross_timeframe_ohlc_mismatch" in {
        finding.code for finding in result.findings
    }


def test_reused_volume_template_is_rejected():
    five = _bars(timedelta(minutes=5), 72, same_volume=True)
    fifteen = tuple(
        ResearchBar(bar.timestamp, bar.open, bar.high, bar.low, bar.close, 100.0)
        for bar in _aggregate(five, 3)
    )
    hourly = tuple(
        ResearchBar(bar.timestamp, bar.open, bar.high, bar.low, bar.close, 100.0)
        for bar in _aggregate(five, 12)
    )
    datasets = {
        "5m": five,
        "15m": fifteen,
        "1h": hourly,
    }
    result = audit_xauusd_multitimeframe(
        datasets,
        policy=_policy(maximum_reused_volume_prefix_pct=90.0),
    )
    assert not result.passed
    assert "reused_volume_sequence" in {finding.code for finding in result.findings}


def test_required_gate_raises_with_finding_codes():
    with pytest.raises(ValueError, match="insufficient_span"):
        require_xauusd_multitimeframe_quality(
            _bundle(), policy=_policy(minimum_span=timedelta(days=1))
        )


def test_policy_and_dataset_keys_are_validated():
    with pytest.raises(ValueError, match="between 0 and 100"):
        XAUUSDQualityPolicy(minimum_aggregation_match_pct=101.0).validate()
    with pytest.raises(ValueError, match="exactly 5m, 15m and 1h"):
        audit_xauusd_multitimeframe({"5m": _bundle()["5m"]}, policy=_policy())
    with pytest.raises(ValueError, match="minimum_weekday_coverage_pct"):
        XAUUSDQualityPolicy(minimum_weekday_coverage_pct=float("nan")).validate()


def test_long_timestamp_span_with_sparse_trading_days_fails_coverage():
    early = _bars(timedelta(minutes=5), 72, start=datetime(2022, 1, 3, tzinfo=timezone.utc))
    late = _bars(timedelta(minutes=5), 72, start=datetime(2025, 1, 6, tzinfo=timezone.utc))
    five = early + late
    datasets = {"5m": five, "15m": _aggregate(five, 3), "1h": _aggregate(five, 12)}
    result = audit_xauusd_multitimeframe(datasets, policy=_policy(minimum_span=timedelta(days=1065)))
    assert not result.passed
    assert "insufficient_span" not in {finding.code for finding in result.findings}
    assert "insufficient_weekday_coverage" in {finding.code for finding in result.findings}
    assert all(summary.weekday_coverage_pct < 1 for summary in result.summaries)


def test_shifted_hourly_labels_fail_even_when_ohlc_matches():
    datasets = dict(_bundle())
    datasets["1h"] = tuple(
        ResearchBar(bar.timestamp + timedelta(minutes=5), bar.open, bar.high,
                    bar.low, bar.close, bar.volume)
        for bar in datasets["1h"]
    )
    result = audit_xauusd_multitimeframe(datasets, policy=_policy())
    assert not result.passed
    assert "off_timeframe_grid" in {finding.code for finding in result.findings}
    assert "insufficient_aggregation_sample" in {finding.code for finding in result.findings}
    assert result.aggregation[-1].compared_bars == 0


def test_saturday_is_checked_in_utc_not_source_timezone():
    from datetime import timezone as tz
    source_zone = tz(timedelta(hours=-3))
    # Friday evening in -03:00 is Saturday in UTC.
    five = _bars(timedelta(minutes=5), 72, start=datetime(2026, 9, 18, 22, tzinfo=source_zone))
    datasets = {"5m": five, "15m": _aggregate(five, 3), "1h": _aggregate(five, 12)}
    result = audit_xauusd_multitimeframe(datasets, policy=_policy())
    assert "saturday_market_data" in {finding.code for finding in result.findings}
