from datetime import datetime, timezone

import pytest

from core.enums import Direction, SetupType, SignalStatus, Timeframe
from core.models import TradeSignal
from core.setup_quality import SetupQualityInput
from core.trade_orchestrator import TradeOrchestrator
from paper_trading.engine import PaperTradingEngine
from risk.risk_budget import RiskBudget


@pytest.mark.parametrize(
    ("field", "value"),
    [("point_value", True), ("point_value", False), ("volume", True), ("volume", False)],
)
def test_orchestrator_rejects_boolean_risk_inputs(field, value):
    engine = PaperTradingEngine(1000, 0.05)
    orchestrator = TradeOrchestrator(engine, RiskBudget(1000, risk_pct=0.01))
    signal = TradeSignal(
        status=SignalStatus.VALID,
        setup_type=SetupType.COMBINED,
        frame=Timeframe.M15,
        direction=Direction.BUY,
        entry_price=100.0,
        sl_price=99.0,
        confidence=0.9,
        aligned=True,
    )
    bars = [
        {
            "timestamp": datetime(2026, 9, 12, 10, i, tzinfo=timezone.utc),
            "open": 99.0,
            "high": 101.0,
            "low": 98.0,
            "close": 100.0,
        }
        for i in range(3)
    ]
    setup = SetupQualityInput(
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
    kwargs = {field: value}

    result = orchestrator.evaluate_and_submit(
        signal,
        bars,
        setup,
        timestamp=datetime(2026, 9, 12, 10, 2, tzinfo=timezone.utc),
        symbol="XAUUSD",
        setup_min_score=70,
        **kwargs,
    )

    assert not result.allowed
    assert result.stage == "risk"
    assert engine.open_order is None
