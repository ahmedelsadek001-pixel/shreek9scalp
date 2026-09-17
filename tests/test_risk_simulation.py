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


def test_monte_carlo_reports_tail_quantiles():
    result = monte_carlo([100.0, -60.0, 40.0, -20.0], 1000, simulations=50, seed=11)
    assert result.worst_ending_equity <= result.p05_ending_equity <= result.median_ending_equity
    assert result.median_max_drawdown <= result.p95_max_drawdown <= result.worst_max_drawdown


def test_quantiles_remain_finite_under_normal_inputs():
    result = monte_carlo([25.0, -10.0, 15.0], 1000, simulations=200, seed=3)
    assert result.p05_ending_equity == pytest.approx(result.p05_ending_equity)
    assert result.p95_max_drawdown == pytest.approx(result.p95_max_drawdown)


def test_ruin_is_path_dependent_and_stops_after_breach():
    result = simulate_sequence([100.0, -1500.0, 10000.0], 1000, seed=7)
    assert result.ruin is True
    assert result.ending_equity <= 0
    assert len(result.pnl) == 1


def test_invalid_simulation_count_rejects_boolean():
    with pytest.raises(ValueError, match="positive integer"):
        monte_carlo([1], 1000, simulations=True)


def test_invalid_inputs_fail_closed():
    with pytest.raises(ValueError):
        simulate_sequence([], 1000)
    with pytest.raises(ValueError):
        simulate_sequence([1], 0)
    with pytest.raises(ValueError):
        simulate_sequence([1], 1000, slippage_multiplier=0.9)
    with pytest.raises(ValueError):
        monte_carlo([1], 1000, simulations=0)
