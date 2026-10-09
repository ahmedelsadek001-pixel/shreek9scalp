from dataclasses import replace
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
    bars.append(ResearchBar(start + timedelta(minutes=27), 100.006, 100.0075, 100.0045, 100.0075, 100.0))
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


def test_diagnostics_preserve_signals_and_identify_first_failed_filter():
    from dataclasses import replace
    diagnostics = {"old": "discard"}
    bars = _bars()
    baseline = detect_breakout_retest(bars, 0.0001)
    assert detect_breakout_retest(bars, 0.0001, diagnostics=diagnostics) == baseline
    assert diagnostics["returned_signals"] == 1
    assert diagnostics["valid_breakouts"] == 1
    assert diagnostics["latest_valid_breakout"]["level"] == baseline[0].breakout_level
    assert "old" not in diagnostics
    for reason, changed in (
        ("consolidation_range", [replace(b, high=b.high + 1) for b in bars]),
        ("breakout_tick_volume", bars[:26] + [replace(bars[26], volume=150)] + bars[27:]),
        ("breakout_body", bars[:26] + [replace(bars[26], open=bars[26].close)] + bars[27:]),
        ("no_pin_or_engulfing_confirmation", bars[:-1] + [replace(bars[-1], open=bars[-1].close)]),
        ("retest_did_not_touch_level", bars[:-1] + [replace(bars[-1], low=100.006)]),
    ):
        assert detect_breakout_retest(changed, 0.0001, min_signal_index=27,
                                     diagnostics=diagnostics) == ()
        assert diagnostics["rejected"][reason] == 1
        assert diagnostics["returned_signals"] == 0


def _repeated_confirmations(direction):
    bars = _bars()
    last = bars[-1]
    bars.extend(replace(last, timestamp=last.timestamp + timedelta(minutes=i))
                for i in range(1, 5))
    if direction is Direction.SELL:
        bars = [replace(bar, open=200 - bar.open, high=200 - bar.low,
                        low=200 - bar.high, close=200 - bar.close) for bar in bars]
    return bars


@pytest.mark.parametrize("direction", [Direction.BUY, Direction.SELL])
@pytest.mark.parametrize("boundary", [0, 26, 27, 28, 29, 30, 31, 32])
def test_boundary_filters_the_same_causal_first_confirmation_stream(direction, boundary):
    bars = _repeated_confirmations(direction)
    complete = detect_breakout_retest(bars, 0.0001)
    assert len(complete) == 1
    assert complete[0].direction is direction
    expected = tuple(signal for signal in complete
                     if signal.signal_time in {bar.timestamp for bar in bars[boundary:]})
    diagnostics = {}
    assert detect_breakout_retest(bars, 0.0001, min_signal_index=boundary,
                                 diagnostics=diagnostics) == expected
    if boundary > 27:
        assert diagnostics["rejected"]["first_confirmation_before_evaluation"] == 1
    from execution.strategy_diagnostics import bounded_diagnostics
    assert bounded_diagnostics(diagnostics)["returned_signals"] == len(expected)


@pytest.mark.parametrize("direction", [Direction.BUY, Direction.SELL])
def test_rolling_last_bar_scans_return_a_breakout_only_once(direction):
    bars = _repeated_confirmations(direction)
    replay = []
    for end in range(27, len(bars)):
        replay.extend(detect_breakout_retest(bars[:end + 1], 0.0001,
                                           min_signal_index=end))
    assert tuple(replay) == detect_breakout_retest(bars, 0.0001)
    assert len(replay) == 1


def test_unconfirmed_warmup_retest_does_not_consume_a_later_first_confirmation():
    bars = _repeated_confirmations(Direction.BUY)
    bars[27] = replace(bars[27], open=bars[27].close)
    signals = detect_breakout_retest(bars, 0.0001, min_signal_index=28)
    assert len(signals) == 1
    assert signals[0].signal_time == bars[28].timestamp
    assert signals == detect_breakout_retest(bars, 0.0001)


def test_consumed_old_breakout_does_not_block_a_new_independent_breakout():
    first = _repeated_confirmations(Direction.BUY)
    second = [replace(bar, timestamp=first[-1].timestamp + timedelta(minutes=i + 1),
                      open=bar.open + 10, high=bar.high + 10,
                      low=bar.low + 10, close=bar.close + 10)
              for i, bar in enumerate(_bars())]
    bars = first + second
    boundary = len(first)
    signals = detect_breakout_retest(bars, 0.0001, min_signal_index=boundary)
    assert len(signals) == 1
    assert signals[0].signal_time == bars[-1].timestamp
    assert signals[0].breakout_time == bars[-2].timestamp
