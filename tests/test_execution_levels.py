from core.enums import Direction, SetupType, Timeframe, SignalStatus
from core.execution_levels import build_execution_levels
from core.models import TradeSignal


def signal(direction, entry, sl):
    return TradeSignal(
        status=SignalStatus.VALID,
        setup_type=SetupType.OB_ENTRY,
        frame=Timeframe.M5,
        direction=direction,
        entry_price=entry,
        sl_price=sl,
        confidence=0.9,
    )


def test_buy_uses_valid_draw_target():
    levels = build_execution_levels(signal(Direction.BUY, 100.0, 98.0), draw_target=104.0)
    assert levels is not None
    assert levels.tp1 == 102.0
    assert levels.tp2 == 104.0
    assert levels.tp3 == 106.0


def test_sell_falls_back_to_two_r_when_draw_target_is_too_close():
    levels = build_execution_levels(signal(Direction.SELL, 100.0, 102.0), draw_target=99.0)
    assert levels is not None
    assert levels.tp1 == 98.0
    assert levels.tp2 == 96.0
    assert levels.tp3 == 94.0


def test_invalid_stop_side_fails_closed():
    assert build_execution_levels(signal(Direction.BUY, 100.0, 101.0)) is None
    assert build_execution_levels(signal(Direction.SELL, 100.0, 99.0)) is None


def test_min_rr_is_enforced_for_draw_target():
    levels = build_execution_levels(signal(Direction.BUY, 100.0, 98.0), draw_target=102.5, min_rr=1.5)
    assert levels is not None
    assert levels.tp2 == 103.0


def test_atr_buffer_widens_stop_away_from_entry():
    levels = build_execution_levels(signal(Direction.BUY, 100.0, 98.0), atr_sl_buffer=0.5)
    assert levels is not None
    assert levels.sl == 97.5
    assert levels.risk == 2.5
