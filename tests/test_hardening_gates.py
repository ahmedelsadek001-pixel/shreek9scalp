from datetime import datetime, timezone

from core.setup_quality import SetupQualityInput
from risk.hardening_gates import news_firewall_gate, setup_quality_gate
from risk.news_firewall import NewsEvent, NewsFirewallPolicy, NewsImpact


def test_setup_quality_gate_blocks_weak_setup():
    result = setup_quality_gate(SetupQualityInput())
    assert not result.allowed


def test_setup_quality_gate_allows_strong_setup():
    setup = SetupQualityInput(True, True, True, True, True, True, True, True, True)
    result = setup_quality_gate(setup)
    assert result.allowed


def test_setup_quality_gate_rejects_invalid_threshold():
    result = setup_quality_gate(SetupQualityInput(), minimum_score=101)
    assert not result.allowed


def test_news_gate_blocks_high_impact_event():
    now = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
    event = NewsEvent(now, NewsImpact.HIGH, frozenset({"USD"}))
    result = news_firewall_gate(NewsFirewallPolicy(), now, [event], ["USD"])
    assert not result.allowed


def test_news_gate_allows_clear_window():
    now = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
    event = NewsEvent(now, NewsImpact.HIGH, frozenset({"EUR"}))
    result = news_firewall_gate(NewsFirewallPolicy(), now, [event], ["USD"])
    assert result.allowed
