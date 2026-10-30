import pytest

from research.regime import Regime, RegimeConfig, classify_regime


def test_strong_directional_window_is_trend():
    assert classify_regime([float(i) for i in range(20)]) is Regime.TREND


def test_choppy_window_is_range():
    values = [100.0, 101.0, 99.0, 100.0, 99.5, 100.5, 99.0, 100.0, 99.5, 100.5]
    values *= 2
    assert classify_regime(values) is Regime.RANGE


def test_insufficient_data_is_unknown():
    assert classify_regime([100.0, 101.0]) is Regime.UNKNOWN


def test_invalid_data_is_unknown():
    assert classify_regime([100.0] * 19 + [float("nan")]) is Regime.UNKNOWN


def test_threshold_validation():
    with pytest.raises(ValueError):
        classify_regime([100.0] * 20, RegimeConfig(trend_efficiency_min=0.2, range_efficiency_max=0.3))
