from datetime import datetime, timezone

import pytest

from core.enums import Direction
from paper_trading.engine import PaperOrder, PaperTradingEngine


def order(direction=Direction.BUY, entry=100.0, sl=99.0):
    return PaperOrder("XAUUSD", direction, entry, sl, 1.0, datetime(2026, 9, 12, 10, tzinfo=timezone.utc))


def test_paper_order_requires_risk_budget_and_closes():
    engine = PaperTradingEngine(1000, 0.05)
    engine.submit(order())
    fill = engine.close(102.0, datetime(2026, 9, 12, 11, tzinfo=timezone.utc), "TP")
    assert fill.pnl == 2.0
    assert engine.open_order is None
    assert len(engine.fills) == 1


def test_paper_engine_rejects_second_open_position():
    engine = PaperTradingEngine()
    engine.submit(order())
    with pytest.raises(RuntimeError):
        engine.submit(order())


def test_daily_budget_blocks_excessive_stop_risk():
    engine = PaperTradingEngine(1000, 0.05)
    engine.submit(order(entry=100, sl=99))
    engine.close(99, datetime(2026, 9, 12, 11, tzinfo=timezone.utc), "SL")
    with pytest.raises(RuntimeError):
        engine.submit(order(entry=100, sl=49))
