from datetime import datetime, timezone

from core.trade_orchestrator import TradeOrchestrator
from paper_trading.engine import PaperTradingEngine
from risk.risk_budget import RiskBudget


def test_orchestrator_rejects_wrong_signal_type_without_raising():
    engine = PaperTradingEngine(1000, 0.05)
    orchestrator = TradeOrchestrator(engine, RiskBudget(1000))

    result = orchestrator.evaluate_and_submit(
        "not-a-trade-signal",
        [],
        None,
        timestamp=datetime(2026, 9, 12, 10, 2, tzinfo=timezone.utc),
        symbol="XAUUSD",
        setup_min_score=70,
    )

    assert not result.allowed
    assert result.stage == "signal"
    assert result.reason == "signal must be TradeSignal"
    assert engine.open_order is None
