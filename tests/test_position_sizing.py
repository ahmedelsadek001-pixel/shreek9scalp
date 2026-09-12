import risk.position_sizing as sizing


class Info:
    trade_tick_size = 0.01
    trade_tick_value = 1.0
    volume_step = 0.01
    volume_min = 0.01
    volume_max = 100.0


def test_sizing_floors_volume(monkeypatch):
    monkeypatch.setattr(sizing.MT5Manager, "ensure_initialized", classmethod(lambda cls: True))
    monkeypatch.setattr(sizing.mt5, "symbol_info", lambda symbol: Info())
    assert sizing.compute_lot_size("XAUUSD", 10, 0.10) == 1.0


def test_sizing_fails_closed_when_minimum_would_exceed_risk(monkeypatch):
    class Tiny(Info):
        volume_min = 1.0
    monkeypatch.setattr(sizing.MT5Manager, "ensure_initialized", classmethod(lambda cls: True))
    monkeypatch.setattr(sizing.mt5, "symbol_info", lambda symbol: Tiny())
    assert sizing.compute_lot_size("XAUUSD", 0.1, 0.10) == 0.0


def test_sizing_fails_closed_without_broker_metadata(monkeypatch):
    monkeypatch.setattr(sizing.MT5Manager, "ensure_initialized", classmethod(lambda cls: True))
    monkeypatch.setattr(sizing.mt5, "symbol_info", lambda symbol: None)
    assert sizing.compute_lot_size("XAUUSD", 10, 1) == 0.0
