from datetime import datetime, timezone

from core.integration_gate import evaluate_pre_trade
from core.setup_quality import SetupQuality
from risk.news_firewall import NewsFirewallPolicy


def _setup(score: int = 80) -> SetupQuality:
    return SetupQuality(score=score, grade="HIGH" if score >= 80 else "VALID")


def _bar(ts: datetime, close: float = 100.0):
    return {"timestamp": ts, "open": 99.0, "high": 101.0, "low": 98.0, "close": close}


def test_integration_gate_allows_valid_chain():
    bars = [_bar(datetime(2026, 9, 12, 10, i, tzinfo=timezone.utc)) for i in range(3)]
    decision = evaluate_pre_trade(
        bars,
        _setup(),
        setup_min_score=70,
        news_events=[],
        news_policy=NewsFirewallPolicy(),
    )
    assert decision.allowed
    assert decision.reasons == ()


def test_integration_gate_blocks_bad_market_data():
    bars = [_bar(datetime(2026, 9, 12, 10, 2, tzinfo=timezone.utc)), _bar(datetime(2026, 9, 12, 10, 1, tzinfo=timezone.utc))]
    decision = evaluate_pre_trade(
        bars,
        _setup(),
        setup_min_score=70,
        news_events=[],
        news_policy=NewsFirewallPolicy(),
    )
    assert not decision.allowed
    assert decision.reasons


def test_integration_gate_blocks_weak_setup():
    bars = [_bar(datetime(2026, 9, 12, 10, i, tzinfo=timezone.utc)) for i in range(3)]
    decision = evaluate_pre_trade(
        bars,
        _setup(50),
        setup_min_score=70,
        news_events=[],
        news_policy=NewsFirewallPolicy(),
    )
    assert not decision.allowed
    assert decision.reasons
