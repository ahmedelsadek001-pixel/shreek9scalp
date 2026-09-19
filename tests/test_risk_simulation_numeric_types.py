import pytest

from core.risk_simulation import _median, _quantile, monte_carlo, simulate_sequence


@pytest.mark.parametrize("equity", [True, False, "1000"])
def test_simulation_rejects_non_numeric_equity_types(equity):
    with pytest.raises(ValueError, match="starting equity"):
        simulate_sequence([1.0], starting_equity=equity)


@pytest.mark.parametrize("pnl", [[True], [False], ["1.0"]])
def test_simulation_rejects_boolean_and_string_pnl(pnl):
    with pytest.raises(ValueError, match="pnl"):
        simulate_sequence(pnl)


@pytest.mark.parametrize("multiplier", [True, False, "1.1"])
def test_simulation_rejects_invalid_cost_multiplier_types(multiplier):
    with pytest.raises(ValueError, match="cost multipliers"):
        simulate_sequence([1.0], slippage_multiplier=multiplier)


@pytest.mark.parametrize("probability", [True, False, "0.5"])
def test_quantile_rejects_boolean_and_string_probability(probability):
    with pytest.raises(ValueError, match="quantile probability"):
        _quantile([1.0, 2.0], probability)


@pytest.mark.parametrize("sample", [[True], [False], ["1.0"]])
def test_aggregators_reject_boolean_and_string_samples(sample):
    with pytest.raises(ValueError, match="sample"):
        _median(sample)
    with pytest.raises(ValueError, match="sample"):
        _quantile(sample, 0.5)


def test_monte_carlo_rejects_boolean_equity_and_pnl():
    with pytest.raises(ValueError, match="starting equity"):
        monte_carlo([1.0], starting_equity=True, simulations=2)
    with pytest.raises(ValueError, match="pnl"):
        monte_carlo([True], simulations=2)
