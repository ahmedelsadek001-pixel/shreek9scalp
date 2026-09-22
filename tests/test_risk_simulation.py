import pytest

from core.risk_simulation import _median, _quantile, monte_carlo, simulate_sequence


def test_simulation_is_reproducible():
    assert simulate_sequence([10.0, -5.0, 20.0, -3.0], 1000, seed=7) == simulate_sequence(
        [10.0, -5.0, 20.0, -3.0], 1000, seed=7
    )


def test_cost_stress_is_more_conservative():
    base = simulate_sequence([100.0, -50.0, 80.0], 1000, seed=1)
    stressed = simulate_sequence(
        [100.0, -50.0, 80.0], 1000, seed=1,
        slippage_multiplier=1.2, spread_multiplier=1.1,
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


def test_median_avoids_intermediate_overflow():
    assert _median([1.7e308, 1.7e308]) == pytest.approx(1.7e308)
    assert _median([-1.7e308, 1.7e308]) == pytest.approx(0.0)


def test_quantile_avoids_overflow_for_opposite_extremes():
    assert _quantile([-1.7e308, 1.7e308], 0.5) == pytest.approx(0.0)


def test_ruin_is_path_dependent_and_stops_after_breach():
    result = simulate_sequence([100.0, -1500.0, 10000.0], 1000, seed=7)
    assert result.ruin is True
    assert result.ending_equity <= 0
    assert len(result.pnl) == 1


def test_invalid_simulation_count_rejects_boolean():
    with pytest.raises(ValueError, match="positive integer"):
        monte_carlo([1], 1000, simulations=True)


def test_invalid_seed_rejects_boolean_and_non_integer_values():
    for seed in (True, 1.5, "42"):
        with pytest.raises(ValueError, match="seed must be an integer or None"):
            simulate_sequence([1.0], 1000, seed=seed)
        with pytest.raises(ValueError, match="seed must be an integer or None"):
            monte_carlo([1.0], 1000, seed=seed)


def test_combined_cost_multiplier_overflow_fails_closed():
    with pytest.raises(ValueError, match="combined cost multiplier must be finite"):
        simulate_sequence([1.0], 1000, slippage_multiplier=1e308, spread_multiplier=1e308)


def test_stressed_trade_pnl_overflow_fails_closed():
    with pytest.raises(ValueError, match="stressed trade P&L must remain finite"):
        simulate_sequence([-1e308], 1000, slippage_multiplier=2.0)


def test_drawdown_percentage_overflow_fails_closed():
    with pytest.raises(ValueError, match="simulated drawdown must remain finite"):
        simulate_sequence([-1e308], starting_equity=1e-308, seed=0)


def test_invalid_inputs_fail_closed():
    with pytest.raises(ValueError):
        simulate_sequence([], 1000)
    with pytest.raises(ValueError):
        simulate_sequence([1], 0)
    with pytest.raises(ValueError):
        simulate_sequence([1], 1000, slippage_multiplier=0.9)
    with pytest.raises(ValueError):
        monte_carlo([1], 1000, simulations=0)


@pytest.mark.parametrize("sample", [[], [2.0, 1.0], [1.0, float("inf")], [float("nan")]])
def test_median_rejects_empty_unsorted_or_nonfinite_samples(sample):
    with pytest.raises(ValueError):
        _median(sample)


@pytest.mark.parametrize("sample", [[], [2.0, 1.0], [1.0, float("inf")], [float("nan")]])
def test_quantile_rejects_empty_unsorted_or_nonfinite_samples(sample):
    with pytest.raises(ValueError):
        _quantile(sample, 0.5)


@pytest.mark.parametrize("probability", [float("nan"), float("inf"), -0.1, 1.1])
def test_quantile_rejects_invalid_probability(probability):
    with pytest.raises(ValueError, match="quantile probability"):
        _quantile([1.0, 2.0], probability)


def test_drawdown_percentage_is_measured_from_running_peak(monkeypatch):
    class FixedRandom:
        def __init__(self, seed):
            pass
        def choice(self, values):
            return values.pop(0)

    monkeypatch.setattr("core.risk_simulation.random.Random", FixedRandom)
    pnl = [1000.0, -500.0]
    result = simulate_sequence(pnl, starting_equity=1000.0, seed=1)
    assert result.max_drawdown == pytest.approx(500.0)
    assert result.max_drawdown_pct == pytest.approx(25.0)
