from datetime import datetime, timezone

from core.enums import Direction
from core.paper_trade_pipeline import admit_and_submit_paper
from core.setup_quality import SetupQualityInput
from paper_trading.engine import PaperTradingEngine
from risk.news_firewall import NewsFirewallPolicy


def _bars():
    return [
        {"timestamp": datetime(2026, 9, 12, 10, i, tzinfo=timezone.utc), "open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0}
        for i in range(3)
    ]


def _setup():
    return SetupQualityInput(
        htf_structure=True, liquidity_sweep=True, fvg=True, order_block=True,
        m15_confirmation=True, m5_confirmation=True, m3_confirmation=True,
        rr_valid=True, session_valid=True,
    )


def _call(engine, setup=None, entry=100.0, sl=99.0):
    return admit_and_submit_paper(
        engine, _bars(), setup or _setup(), timestamp=datetime(2026, 9, 12, 10, 2, tzinfo=timezone.utc),
        symbol="XAUUSD", direction=Direction.BUY, entry=entry, sl=sl, volume=1.0,
        setup_min_score=70, news_events=[], currencies=[], news_policy=NewsFirewallPolicy(),
    )


def test_pipeline_admits_and_submits():
    engine = PaperTradingEngine(1000, 0.05)
    result = _call(engine)
    assert result.allowed
    assert result.stage == "paper_execution"
    assert engine.open_order is not None


def test_pipeline_blocks_before_execution_on_weak_setup():
    engine = PaperTradingEngine(1000, 0.05)
    result = _call(engine, SetupQualityInput(htf_structure=True))
    assert not result.allowed
    assert result.stage == "admission"
    assert engine.open_order is None


def test_pipeline_blocks_on_daily_risk_before_execution():
    engine = PaperTradingEngine(1000, 0.05)
    engine.ledger.record(datetime(2026, 9, 12, tzinfo=timezone.utc).date(), -49.5)
    result = _call(engine, entry=100.0, sl=99.0)
    assert not result.allowed
    assert result.stage == "risk"
    assert engine.open_order is None
