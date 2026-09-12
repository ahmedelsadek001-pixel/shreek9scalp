import pytest

from core.enums import Direction
from research.mae_mfe import measure_excursion


def test_buy_excursion():
    result = measure_excursion(Direction.BUY, 100.0, 105.0, [101, 103, 106], [99, 100, 102])
    assert result.mae == pytest.approx(1.0)
    assert result.mfe == pytest.approx(6.0)


def test_sell_excursion():
    result = measure_excursion(Direction.SELL, 100.0, 95.0, [101, 103, 99], [98, 96, 94])
    assert result.mae == pytest.approx(3.0)
    assert result.mfe == pytest.approx(6.0)


def test_invalid_ohlc_is_rejected():
    with pytest.raises(ValueError):
        measure_excursion(Direction.BUY, 100.0, 101.0, [100], [101])


def test_mismatched_series_are_rejected():
    with pytest.raises(ValueError):
        measure_excursion(Direction.BUY, 100.0, 101.0, [101, 102], [99])
