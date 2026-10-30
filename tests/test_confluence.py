from config.settings import Settings
from core.confluence import evaluate_confluence
from core.enums import Direction, StructureEvent, Timeframe
from core.models import MarketStructure, TradeSignal
from core.enums import SignalStatus, SetupType


def _s(tf, direction, event=StructureEvent.NONE):
    return MarketStructure(tf, direction, event, 2100.0, 1900.0, False)


def _signal():
    return TradeSignal(
        SignalStatus.VALID, SetupType.COMBINED, Timeframe.M5,
        Direction.BUY, 2000.0, 1990.0, 0.95, "test",
        candle_confirmation=True, bos_confirmed=True,
        sweep_confirmed=True,
    )


def test_htf_conflict_is_never_tradable():
    decision = evaluate_confluence(
        Direction.BUY,
        _s(Timeframe.D1, Direction.BUY),
        _s(Timeframe.H4, Direction.SELL),
        _s(Timeframe.H1, Direction.BUY),
        _s(Timeframe.M15, Direction.BUY, StructureEvent.BOS_BULLISH),
        _signal(),
        in_pd_zone=True,
        killzone_active=True,
        draw_on_liquidity=True,
    )
    assert not decision.tradable
    assert "HTF" in decision.reason


def test_missing_signal_is_not_tradable():
    decision = evaluate_confluence(
        Direction.BUY,
        _s(Timeframe.D1, Direction.BUY),
        _s(Timeframe.H4, Direction.BUY),
        _s(Timeframe.H1, Direction.BUY),
        _s(Timeframe.M15, Direction.BUY, StructureEvent.BOS_BULLISH),
        None,
    )
    assert not decision.tradable


def test_score_below_threshold_is_not_tradable():
    settings = Settings(confluence_threshold=99)
    decision = evaluate_confluence(
        Direction.BUY,
        _s(Timeframe.D1, Direction.BUY),
        _s(Timeframe.H4, Direction.BUY),
        _s(Timeframe.H1, Direction.BUY),
        _s(Timeframe.M15, Direction.BUY, StructureEvent.BOS_BULLISH),
        _signal(),
        settings=settings,
    )
    assert not decision.tradable
