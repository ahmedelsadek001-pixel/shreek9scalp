import pytest

from paper_trading.engine import PaperOrder, PaperTradingEngine


def order():
    return PaperOrder("XAUUSD", "LONG", 100.0, 99.0, 102.0, 0.5)


def test_rejected_order_never_opens():
    engine = PaperTradingEngine(1000)
    assert engine.submit(order(), admitted=False) is False
    assert engine.open_order is None
    assert engine.equity == 1000


def test_admitted_order_closes_and_updates_equity():
    engine = PaperTradingEngine(1000)
    assert engine.submit(order(), admitted=True) is True
    fill = engine.close(102.0, "TP")
    assert fill.realized_pnl == pytest.approx(1.0)
    assert engine.equity == pytest.approx(1001.0)
    assert engine.open_order is None


def test_second_position_is_blocked_until_close():
    engine = PaperTradingEngine()
    engine.submit(order(), admitted=True)
    with pytest.raises(RuntimeError):
        engine.submit(order(), admitted=True)


def test_invalid_order_geometry_fails_closed():
    with pytest.raises(ValueError):
        PaperOrder("XAUUSD", "LONG", 100, 101, 102, 1).validate()
    with pytest.raises(ValueError):
        PaperOrder("XAUUSD", "SHORT", 100, 99, 98, 1).validate()
