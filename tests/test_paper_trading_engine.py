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


def test_close_rejects_invalid_exit_without_mutating_position():
    engine = PaperTradingEngine()
    engine.submit(order())

    with pytest.raises(ValueError, match="exit price must be positive and finite"):
        engine.close("not-a-number", datetime(2026, 9, 12, 11, tzinfo=timezone.utc))

    assert engine.open_order == order()
    assert engine.fills == []
    assert engine.ledger.realized(datetime(2026, 9, 12, tzinfo=timezone.utc).date()) == 0.0


@pytest.mark.parametrize("field,value", [("entry", None), ("entry", "bad"), ("sl", float("nan")), ("volume", float("inf")), ("volume", 0), ("volume", -1)])
def test_submit_rejects_invalid_numeric_fields(field, value):
    values = {"entry": 100.0, "sl": 99.0, "volume": 1.0}
    values[field] = value
    engine = PaperTradingEngine()
    with pytest.raises(ValueError):
        engine.submit(PaperOrder("XAUUSD", Direction.BUY, values["entry"], values["sl"], values["volume"], datetime(2026, 9, 12, 10, tzinfo=timezone.utc)))
    assert engine.open_order is None


def test_submit_normalizes_numeric_strings():
    engine = PaperTradingEngine()
    engine.submit(PaperOrder("XAUUSD", Direction.BUY, "100", "99", "1.5", datetime(2026, 9, 12, 10, tzinfo=timezone.utc)))
    assert engine.open_order.entry == 100.0
    assert engine.open_order.sl == 99.0
    assert engine.open_order.volume == 1.5
