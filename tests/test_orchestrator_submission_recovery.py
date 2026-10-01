from datetime import datetime, timezone

from core.enums import Direction, SetupType, SignalStatus, Timeframe
from core.models import TradeSignal
from core.setup_quality import SetupQualityInput
from core.trade_orchestrator import TradeOrchestrator
from paper_trading.engine import PaperTradingEngine
from risk.risk_budget import RiskBudget


def _bars():
    return [
        {
            "timestamp": datetime(2026, 9, 12, 10, i, tzinfo=timezone.utc),
            "open": 99.0,
            "high": 101.0,
            "low": 98.0,
            "close": 100.0,
        }
        for i in range(3)
    ]


def _setup():
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


def _signal():
    return TradeSignal(
        status=SignalStatus.VALID,
        setup_type=SetupType.COMBINED,
        frame=Timeframe.M15,
        direction=Direction.BUY,
        entry_price=100.0,
        sl_price=99.0,
        confidence=0.9,
        aligned=True,
    )


def test_unexpected_submit_exception_releases_duplicate_reservation():
    engine = PaperTradingEngine(1000, 0.05)
    orchestrator = TradeOrchestrator(engine, RiskBudget(1000, risk_pct=0.01))
    original_submit = engine.submit

    def fail_unexpectedly(_order):
        raise LookupError("unexpected adapter failure")

    engine.submit = fail_unexpectedly
    failed = orchestrator.evaluate_and_submit(
        _signal(), _bars(), _setup(),
        timestamp=datetime(2026, 9, 12, 10, 2, tzinfo=timezone.utc),
        symbol="XAUUSD", setup_min_score=70,
    )

    assert not failed.allowed
    assert failed.stage == "paper_execution"
    assert failed.reason == "unexpected adapter failure"
    assert failed.fingerprint

    engine.submit = original_submit
    retried = orchestrator.evaluate_and_submit(
        _signal(), _bars(), _setup(),
        timestamp=datetime(2026, 9, 12, 10, 2, tzinfo=timezone.utc),
        symbol="XAUUSD", setup_min_score=70,
    )
    assert retried.allowed
