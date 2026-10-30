from datetime import datetime, timedelta, timezone

from core.admission_firewall import validate_trade_admission
from core.setup_quality import SetupQualityInput
from risk.news_firewall import NewsEvent, NewsFirewallPolicy, NewsImpact


def bars():
    t = datetime(2026, 9, 12, 10, tzinfo=timezone.utc)
    return [
        {"timestamp": t, "open": 100, "high": 101, "low": 99, "close": 100.5},
        {"timestamp": t + timedelta(minutes=1), "open": 100.5, "high": 102, "low": 100, "close": 101},
    ]


def good_setup():
    return SetupQualityInput(True, True, True, True, True, True, False, True, True)


def test_firewall_accepts_clean_high_quality_setup():
    result = validate_trade_admission(bars(), good_setup(), datetime(2026, 9, 12, 10, 2, tzinfo=timezone.utc))
    assert result.allowed
    assert result.setup_score >= 70


def test_firewall_blocks_low_quality_setup():
    result = validate_trade_admission(bars(), SetupQualityInput(), datetime(2026, 9, 12, 10, 2, tzinfo=timezone.utc))
    assert not result.allowed
    assert "quality" in result.reason


def test_firewall_blocks_matching_high_impact_news():
    now = datetime(2026, 9, 12, 10, 2, tzinfo=timezone.utc)
    event = NewsEvent(now + timedelta(minutes=3), NewsImpact.HIGH, frozenset({"USD"}))
    result = validate_trade_admission(
        bars(), good_setup(), now,
        [event], ["USD"], NewsFirewallPolicy(before_minutes=15, after_minutes=15),
    )
    assert not result.allowed
    assert "news" in result.reason


def test_firewall_blocks_bad_market_data():
    broken = bars()
    broken[1]["timestamp"] = broken[0]["timestamp"]
    result = validate_trade_admission(broken, good_setup(), datetime(2026, 9, 12, 10, 2, tzinfo=timezone.utc))
    assert not result.allowed
    assert "market-data" in result.reason
