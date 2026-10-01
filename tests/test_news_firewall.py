from datetime import datetime, timedelta, timezone

import pytest

from risk.news_firewall import NewsEvent, NewsFirewallPolicy, NewsImpact


UTC = timezone.utc


def test_high_impact_blocks_before_and_after():
    event_time = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
    event = NewsEvent(event_time, NewsImpact.HIGH, frozenset({"USD"}))
    policy = NewsFirewallPolicy(before_minutes=15, after_minutes=15)
    assert policy.blocked(event_time - timedelta(minutes=15), [event], ["USD"])
    assert policy.blocked(event_time + timedelta(minutes=15), [event], ["USD"])
    assert not policy.blocked(event_time + timedelta(minutes=16), [event], ["USD"])


def test_lower_impact_is_ignored():
    now = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
    event = NewsEvent(now, NewsImpact.MEDIUM, frozenset({"USD"}))
    assert not NewsFirewallPolicy().blocked(now, [event], ["USD"])


def test_unrelated_currency_is_ignored():
    now = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
    event = NewsEvent(now, NewsImpact.HIGH, frozenset({"EUR"}))
    assert not NewsFirewallPolicy().blocked(now, [event], ["USD"])


def test_global_event_blocks_without_currency_match():
    now = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
    event = NewsEvent(now, NewsImpact.HIGH)
    assert NewsFirewallPolicy().blocked(now, [event], ["XAUUSD"])


def test_require_clear_fails_closed():
    now = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
    event = NewsEvent(now, NewsImpact.HIGH, frozenset({"USD"}))
    with pytest.raises(RuntimeError, match="news firewall"):
        NewsFirewallPolicy().require_clear(now, [event], ["USD"])


def test_naive_timestamp_is_rejected():
    with pytest.raises(ValueError):
        NewsEvent(datetime(2026, 9, 12, 12, 0), NewsImpact.HIGH)
