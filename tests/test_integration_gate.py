from datetime import datetime, timezone

from core.integration_gate import evaluate_pre_trade
from core.setup_quality import SetupQualityInput
from risk.news_firewall import NewsFirewallPolicy


def _setup() -> SetupQualityInput:
    return SetupQualityInput(
        htf_structure=True,
        liquidity_sweep=True,
        fvg=True,
        order_block=True,
        m15_confirmation=True,
        m5_confirmation=True,
        m3_confirmation=True,
        rr_valid=True,
        session_valid=True,
    )


def _bar(ts: datetime):
    return {"timestamp": ts, "open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0}


def _kwargs():
    return dict(
        timestamp=datetime(2026, 9, 12, 10, 2, tzinfo=timezone.utc),
        setup_min_score=70,
        news_events=[],
        currencies=[],
        news_policy=NewsFirewallPolicy(),
    )


def test_integration_gate_allows_valid_chain():
    bars = [_bar(datetime(2026, 9, 12, 10, i, tzinfo=timezone.utc)) for i in range(3)]
    decision = evaluate_pre_trade(bars, _setup(), **_kwargs())
    assert decision.allowed
    assert decision.reasons == ()


def test_integration_gate_blocks_bad_market_data():
    bars = [_bar(datetime(2026, 9, 12, 10, 2, tzinfo=timezone.utc)), _bar(datetime(2026, 9, 12, 10, 1, tzinfo=timezone.utc))]
    decision = evaluate_pre_trade(bars, _setup(), **_kwargs())
    assert not decision.allowed
    assert decision.reasons


def test_integration_gate_blocks_weak_setup():
    weak = SetupQualityInput(htf_structure=True, liquidity_sweep=True, fvg=True)
    bars = [_bar(datetime(2026, 9, 12, 10, i, tzinfo=timezone.utc)) for i in range(3)]
    decision = evaluate_pre_trade(bars, weak, **_kwargs())
    assert not decision.allowed
    assert decision.reasons
