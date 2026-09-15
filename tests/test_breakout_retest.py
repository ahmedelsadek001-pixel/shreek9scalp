from datetime import datetime, timedelta, timezone

import pytest

from core.enums import Direction
from research.breakout_retest import ResearchBar, detect_breakout_retest


def _bars() -> list[ResearchBar]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars = []
    for i in range(20):
        bars.append(ResearchBar(start + timedelta(minutes=i), 100.003, 100.005, 100.002, 100.004, 100.0))
    for i in range(6):
        bars.append(ResearchBar(start + timedelta(minutes=20 + i), 100.003, 100.005, 100.002, 100.004, 100.0))
    bars.append(ResearchBar(start + timedelta(minutes=26), 100.003, 100.008, 100.0025, 100.0075, 200.0))
    bars.append(ResearchBar(start + timedelta(minutes=27), 100.006, 100.0075, 100.0045, 100.007, 100.0))
    return bars


def test_detects_completed_breakout_retest_without_future_bars():
    signals = detect_breakout_retest(_bars(), pip_size=0.0001)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.direction is Direction.BUY
    assert signal.breakout_level == pytest.approx(100.005)
    assert signal.confirmation == "Pin Bar"
    assert signal.signal_time == _bars()[-1].timestamp
    assert signal.tp3 > signal.tp2 > signal.tp1 > signal.entry_price > signal.sl_price


def test_future_bar_cannot_change_completed_signal():
    bars = _bars()
    baseline = detect_breakout_retest(bars, pip_size=0.0001)
    future = ResearchBar(
        bars[-1].timestamp + timedelta(minutes=1),
        100.007,
        101.0,
        99.0,
        100.5,
        999999.0,
    )

    changed = detect_breakout_retest(bars + [future], pip_size=0.0001)

    assert changed[:1] == baseline


def test_signal_converts_to_backtest_order():
    signal = detect_breakout_retest(_bars(), pip_size=0.0001)[0]
    order = signal.to_backtest_order(volume=0.03)

    assert order.direction is Direction.BUY
    assert order.volume == pytest.approx(0.03)
    assert order.levels.entry == pytest.approx(signal.entry_price)
    assert order.levels.sl == pytest.approx(signal.sl_price)
    assert order.levels.tp3 == pytest.approx(signal.tp3)
    assert order.tag == "breakout_retest"


def test_invalid_pip_size_is_rejected():
    with pytest.raises(ValueError):
        detect_breakout_retest(_bars(), pip_size=0)
