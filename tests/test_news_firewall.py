from datetime import datetime, timedelta, timezone

import pytest

from risk.news_firewall import NewsEvent, NewsFirewallPolicy, NewsImpact


def test_high_impact_blocks_before_and_after():
    event_time = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
    event = NewsEvent(event_time, NewsImpact.HIGH, frozenset({"USD"}), "CPI")
    policy = NewsFirewallPolicy(before_minutes=15, after_minutes=10)
    assert policy.blocked(event_time - timedelta(minutes=15), [event], ["USD"])
    assert policy.blocked(event_time + timedelta(minutes=10), [event], ["USD"])
    assert not policy.blocked(event_time + timedelta(minutes=11), [event], ["USD"])


def test_lower_impact_does_not_block():
    event = NewsEvent(datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc), NewsImpact.MEDIUM, frozenset({"USD"}))
    assert not NewsFirewallPolicy().blocked(event.timestamp, [event], ["USD"])


def test_currency_filter_ignores_unrelated_event():
    event = NewsEvent(datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc), NewsImpact.HIGH, frozenset({"EUR"}))
    assert not NewsFirewallPolicy().blocked(event.timestamp, [event], ["USD"])


def test_empty_event_currency_is_global():
    event = NewsEvent(datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc), NewsImpact.HIGH)
    assert NewsFirewallPolicy().blocked(event.timestamp, [event], ["USD"])


def test_require_clear_fails_closed():
    event = NewsEvent(datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc), NewsImpact.HIGH)
    with pytest.raises(RuntimeError, match="news firewall active"):
        NewsFirewallPolicy().require_clear(event.timestamp, [event])
