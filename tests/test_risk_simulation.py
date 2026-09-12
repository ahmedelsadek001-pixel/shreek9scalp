import pytest
from core.risk_simulation import monte_carlo, simulate_sequence


def test_simulation_is_reproducible():
    pnl = [10.0, -5.0, 20.0, -3.0]
    assert simulate_sequence(pnl, 1000, seed=7) == simulate_sequence(pnl, 1000, seed=7)


def test_cost_stress_is_more_conservative():
    pnl = [100.0, -50.0, 80.0]
    base = simulate_sequence(pnl, 1000, seed=1)
    stressed = simulate_sequence(pnl, 1000, seed=1, slippage_multiplier=1.2, spread_multiplier=1.1)
    assert stressed.ending_equity < base.ending_equity


def test_clustered_bootstrap_is_reproducible():
    pnl = [100.0, -60.0, -70.0, 80.0, 40.0]
    a = monte_carlo(pnl, 1000, simulations=50, seed=11, block_size=2)
    assert a == monte_carlo(pnl, 1000, simulations=50, seed=11, block_size=2)
    assert a.simulations == 50


def test_block_size_one_matches_original_bootstrap_contract():
    pnl = [100.0, -60.0, 40.0, -20.0]
    assert monte_carlo(pnl, 1000, simulations=50, seed=11) == monte_carlo(
        pnl, 1000, simulations=50, seed=11, block_size=1
    )


def test_invalid_inputs_fail_closed():
    with pytest.raises(ValueError):
        simulate_sequence([], 1000)
    with pytest.raises(ValueError):
        simulate_sequence([1], 0)
    with pytest.raises(ValueError):
        simulate_sequence([1], 1000, slippage_multiplier=0.9)
    with pytest.raises(ValueError):
        simulate_sequence([1], 1000, block_size=2)
    with pytest.raises(ValueError):
        simulate_sequence([1], 1000, block_size=0)
    with pytest.raises(ValueError):
        monte_carlo([1], 1000, simulations=0)
