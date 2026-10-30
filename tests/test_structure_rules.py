from core.enums import Direction, StructureEvent
from core.structure_rules import classify_break

def test_bullish_break_from_bearish_bias_is_choch():
    d = classify_break(105.0, 100.0, 95.0, 2.0, 1.0, Direction.SELL)
    assert d.event == StructureEvent.CHOCH_BULLISH
    assert d.bias == Direction.BUY

def test_bearish_break_from_bullish_bias_is_choch():
    d = classify_break(90.0, 105.0, 95.0, 2.0, 1.0, Direction.BUY)
    assert d.event == StructureEvent.CHOCH_BEARISH
    assert d.bias == Direction.SELL

def test_small_break_is_ignored():
    d = classify_break(101.0, 100.0, 95.0, 2.0, 1.0, Direction.BUY)
    assert d.event == StructureEvent.NONE
