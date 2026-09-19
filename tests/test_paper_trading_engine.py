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


@pytest.mark.parametrize("malformed", [None, object()])
def test_submit_rejects_non_paper_order(malformed):
    engine = PaperTradingEngine()
    with pytest.raises(ValueError, match="order must be a PaperOrder"):
        engine.submit(malformed)
    assert engine.open_order is None


def test_submit_rejects_non_datetime_timestamp_without_mutation():
    engine = PaperTradingEngine()
    valid = order()
    malformed = PaperOrder(valid.symbol, valid.direction, valid.entry, valid.sl, valid.volume, "2026-09-12T10:00:00Z")
    with pytest.raises(ValueError, match="order timestamp must be a datetime"):
        engine.submit(malformed)
    assert engine.open_order is None


def test_close_rejects_non_datetime_timestamp_without_mutation():
    engine = PaperTradingEngine()
    engine.submit(order())
    with pytest.raises(ValueError, match="fill timestamp must be a datetime"):
        engine.close(101.0, "2026-09-12T11:00:00Z")
    assert engine.open_order == order()
    assert engine.fills == []


def test_close_rolls_back_ledger_if_risk_state_update_raises(monkeypatch):
    engine = PaperTradingEngine()
    position = order()
    engine.submit(position)
    day = datetime(2026, 9, 12, tzinfo=timezone.utc).date()
    initial_state = engine.risk_state.state
    initial_losses = engine.risk_state.consecutive_losses

    def fail_record_result(_pnl):
        raise RuntimeError("simulated risk-state failure")

    monkeypatch.setattr(engine.risk_state, "record_result", fail_record_result)
    with pytest.raises(RuntimeError, match="simulated risk-state failure"):
        engine.close(98.0, datetime(2026, 9, 12, 11, tzinfo=timezone.utc), "SL")

    assert engine.open_order == position
    assert engine.fills == []
    assert engine.ledger.realized(day) == 0.0
    assert engine.risk_state.state is initial_state
    assert engine.risk_state.consecutive_losses == initial_losses


@pytest.mark.parametrize("symbol", [None, "", "   "])
def test_submit_rejects_empty_or_invalid_symbol(symbol):
    engine = PaperTradingEngine()
    valid = order()
    malformed = PaperOrder(symbol, valid.direction, valid.entry, valid.sl, valid.volume, valid.timestamp)
    with pytest.raises(ValueError, match="order symbol must be a non-empty string"):
        engine.submit(malformed)
    assert engine.open_order is None


def test_submit_strips_symbol_whitespace():
    engine = PaperTradingEngine()
    valid = order()
    engine.submit(PaperOrder(" XAUUSD ", valid.direction, valid.entry, valid.sl, valid.volume, valid.timestamp))
    assert engine.open_order.symbol == "XAUUSD"


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_close_rejects_empty_or_invalid_reason_without_mutation(reason):
    engine = PaperTradingEngine()
    position = order()
    engine.submit(position)
    with pytest.raises(ValueError, match="close reason must be a non-empty string"):
        engine.close(101.0, datetime(2026, 9, 12, 11, tzinfo=timezone.utc), reason)
    assert engine.open_order == position
    assert engine.fills == []


def test_close_strips_reason_whitespace():
    engine = PaperTradingEngine()
    engine.submit(order())
    fill = engine.close(101.0, datetime(2026, 9, 12, 11, tzinfo=timezone.utc), " TP ")
    assert fill.reason == "TP"
