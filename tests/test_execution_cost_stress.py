import pytest

from core.execution_cost_stress import stress_execution_costs


def test_cost_stress_scales_spread_and_slippage_but_not_commission():
    result = stress_execution_costs(
        [10.0, -4.0], [0.5, 0.5], [0.1, 0.1], [0.2, 0.2],
        spread_multiplier=1.5, slippage_multiplier=2.0,
    )
    assert result.baseline_net_pnl == pytest.approx((9.2, -4.8))
    assert result.stressed_net_pnl == pytest.approx((9.0, -5.05))
    assert result.total_commission == pytest.approx(0.4)


def test_unit_multipliers_reproduce_baseline_net_pnl():
    result = stress_execution_costs([5.0, -2.0], [0.2, 0.3], [0.1, 0.1], [0.2, 0.2])
    assert result.stressed_net_pnl == result.baseline_net_pnl
    assert result.total_stressed_net_pnl == pytest.approx(result.total_baseline_net_pnl)


@pytest.mark.parametrize("arguments", [
    ([], [], [], []),
    ([1.0], [], [0.1], [0.1]),
    ([1.0, 2.0], [0.1], [0.1, 0.1], [0.1, 0.1]),
])
def test_cost_stress_rejects_empty_or_mismatched_samples(arguments):
    with pytest.raises(ValueError, match="equal non-zero length"):
        stress_execution_costs(*arguments)


@pytest.mark.parametrize("costs", [
    ([-0.1], [0.1], [0.1]),
    ([0.1], [float("nan")], [0.1]),
    ([0.1], [0.1], [float("inf")]),
])
def test_cost_stress_rejects_invalid_cost_components(costs):
    with pytest.raises(ValueError):
        stress_execution_costs([1.0], *costs)


@pytest.mark.parametrize("spread,slippage", [(0.9, 1.0), (1.0, 0.9), (float("nan"), 1.0), (1.0, float("inf"))])
def test_cost_stress_rejects_invalid_multipliers(spread, slippage):
    with pytest.raises(ValueError, match="multipliers"):
        stress_execution_costs([1.0], [0.1], [0.1], [0.1],
                               spread_multiplier=spread, slippage_multiplier=slippage)


def test_cost_stress_rejects_boolean_as_numeric_input():
    with pytest.raises(ValueError):
        stress_execution_costs([True], [0.1], [0.1], [0.1])


def test_cost_stress_fails_closed_on_aggregate_overflow():
    with pytest.raises(ValueError, match="aggregate"):
        stress_execution_costs([1.0e308, 1.0e308], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0])
