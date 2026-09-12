from datetime import datetime, timezone

from core.enums import Direction, SetupType, SignalStatus, Timeframe
from core.models import TradeSignal
from core.setup_quality import SetupQualityInput
from core.trade_orchestrator import TradeOrchestrator
from paper_trading.engine import PaperTradingEngine
from risk.risk_budget import RiskBudget


TIMESTAMP = datetime(2026, 9, 12, 10, 2, tzinfo=timezone.utc)


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


def _signal(entry=100.0, stop=99.0):
    return TradeSignal(
        status=SignalStatus.VALID,
        setup_type=SetupType.COMBINED,
        frame=Timeframe.M15,
        direction=Direction.BUY,
        entry_price=entry,
        sl_price=stop,
        confidence=0.9,
        aligned=True,
    )


def test_orchestrator_admits_sizes_and_submits():
    engine = PaperTradingEngine(1000, 0.05)
    orchestrator = TradeOrchestrator(engine, RiskBudget(1000, risk_pct=0.01))

    result = orchestrator.evaluate_and_submit(
        _signal(), _bars(), _setup(), timestamp=TIMESTAMP, symbol="XAUUSD", setup_min_score=70
    )

    assert result.allowed
    assert result.stage == "paper_execution"
    assert result.volume == 10.0
    assert engine.open_order is not None


def test_orchestrator_blocks_invalid_signal_before_market_admission():
    engine = PaperTradingEngine(1000, 0.05)
    orchestrator = TradeOrchestrator(engine, RiskBudget(1000))
    invalid = _signal()
    invalid.status = SignalStatus.WAIT

    result = orchestrator.evaluate_and_submit(
        invalid, _bars(), _setup(), timestamp=TIMESTAMP, symbol="XAUUSD", setup_min_score=70
    )

    assert not result.allowed
    assert result.stage == "signal"
    assert engine.open_order is None


def test_orchestrator_blocks_when_risk_budget_is_exceeded():
    engine = PaperTradingEngine(1000, 0.05)
    orchestrator = TradeOrchestrator(engine, RiskBudget(1000, risk_pct=0.01))

    result = orchestrator.evaluate_and_submit(
        _signal(entry=100.0, stop=90.0),
        _bars(),
        _setup(),
        timestamp=TIMESTAMP,
        symbol="XAUUSD",
        setup_min_score=70,
        volume=2.0,
    )

    assert not result.allowed
    assert result.stage == "risk"
    assert engine.open_order is None


def test_orchestrator_blocks_timezone_naive_timestamp():
    engine = PaperTradingEngine(1000, 0.05)
    orchestrator = TradeOrchestrator(engine, RiskBudget(1000))

    result = orchestrator.evaluate_and_submit(
        _signal(), _bars(), _setup(), timestamp=datetime(2026, 9, 12, 10, 2),
        symbol="XAUUSD", setup_min_score=70
    )

    assert not result.allowed
    assert result.stage == "input"
    assert engine.open_order is None
