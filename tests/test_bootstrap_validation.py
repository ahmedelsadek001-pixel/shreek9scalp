import pytest

from research.bootstrap_validation import bootstrap_expectancy


def test_bootstrap_is_reproducible():
    pnl = [2.0, -1.0, 3.0, -2.0, 4.0, -1.0]
    first = bootstrap_expectancy(pnl, simulations=500, seed=11)
    second = bootstrap_expectancy(pnl, simulations=500, seed=11)
    assert first == second
    assert first.samples == 6
    assert first.simulations == 500


def test_positive_sample_has_positive_observed_expectancy():
    report = bootstrap_expectancy([1.0, 2.0, 3.0, 4.0], simulations=500, seed=7)
    assert report.observed_expectancy == pytest.approx(2.5)
    assert report.positive_expectancy_probability == 1.0
    assert report.lower_ci > 0


def test_invalid_inputs_fail_closed():
    with pytest.raises(ValueError):
        bootstrap_expectancy([1.0], simulations=500)
    with pytest.raises(ValueError):
        bootstrap_expectancy([1.0, float("nan")], simulations=500)
    with pytest.raises(ValueError):
        bootstrap_expectancy([1.0, 2.0], simulations=99)
    with pytest.raises(ValueError):
        bootstrap_expectancy([1.0, 2.0], simulations=500, confidence=1.0)
