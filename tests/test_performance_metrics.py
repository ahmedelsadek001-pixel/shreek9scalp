import pytest

from research.performance_metrics import calculate_metrics


def test_performance_metrics():
    report = calculate_metrics([2.0, -1.0, 3.0, -2.0])
    assert report.samples == 4
    assert report.net_pnl == pytest.approx(2.0)
    assert report.expectancy == pytest.approx(0.5)
    assert report.win_rate == pytest.approx(50.0)
    assert report.profit_factor == pytest.approx(5.0 / 3.0)
    # Payoff ratio is mean winner divided by mean loser: 2.5 / 1.5 = 5/3.
    assert report.payoff_ratio == pytest.approx(5.0 / 3.0)
    assert report.max_consecutive_losses == 1


def test_empty_and_non_finite_rejected():
    with pytest.raises(ValueError):
        calculate_metrics([])
    with pytest.raises(ValueError):
        calculate_metrics([1.0, float("nan")])
