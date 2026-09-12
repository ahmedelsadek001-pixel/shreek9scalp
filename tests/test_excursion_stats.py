import pytest

from research.excursion_stats import summarize_excursions
from research.mae_mfe import TradeExcursion


def test_excursion_summary():
    rows = [
        TradeExcursion(100.0, 101.0, 1.0, 4.0),
        TradeExcursion(100.0, 102.0, 2.0, 5.0),
        TradeExcursion(100.0, 99.0, 3.0, 6.0),
    ]
    report = summarize_excursions(rows)
    assert report.samples == 3
    assert report.median_mae == 2.0
    assert report.median_mfe == 5.0
    assert report.p90_mae == pytest.approx(2.8)
    assert report.p90_mfe == pytest.approx(5.8)
    assert report.median_mfe_mae_ratio == pytest.approx(2.5)


def test_empty_input_rejected():
    with pytest.raises(ValueError):
        summarize_excursions([])
