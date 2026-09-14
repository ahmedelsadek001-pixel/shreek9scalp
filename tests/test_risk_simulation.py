import pytest

from core.risk_simulation import monte_carlo, simulate_sequence


def test_simulation_is_reproducible():
    assert simulate_sequence([10.0, -5.0, 20.0, -3.0], 1000, seed=7) == simulate_sequence(
        [10.0, -5.0, 20.0, -3.0], 1000, seed=7
    )


def test_cost_stress_is_more_conservative():
    base = simulate_sequence([100.0, -50.0, 80.0], 1000, seed=1)
    stressed = simulate_sequence(
        [100.0, -50.0, 80.0],
        1000,
        seed=1,
        slippage_multiplier=1.2,
        spread_multiplier=1.1,
    )
    assert stressed.ending_equity < base.ending_equity


def test_monte_carlo_summary_is_reproducible():
    a = monte_carlo([100.0, -60.0, 40.0, -20.0], 1000, simulations=50, seed=11)
    assert a == monte_carlo([100.0, -60.0, 40.0, -20.0], 1000, simulations=50, seed=11)
    assert a.simulations == 50


def test_ruin_is_path_dependent_and_stops_after_breach():
    result = simulate_sequence([100.0, -1500.0, 10000.0], 1000, seed=1)
    assert result.ruin is True
    assert result.ending_equity <= 0
    assert len(result.pnl) == 2


def test_invalid_inputs_fail_closed():
    with pytest.raises(ValueError):
        simulate_sequence([], 1000)
    with pytest.raises(ValueError):
        simulate_sequence([1], 0)
    with pytest.raises(ValueError):
        simulate_sequence([1], 1000, slippage_multiplier=0.9)
    with pytest.raises(ValueError):
        monte_carlo([1], 1000, simulations=0)
