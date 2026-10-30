import pytest

from core.robustness import RobustnessPolicy


@pytest.mark.parametrize(
    "policy",
    [
        RobustnessPolicy(min_wfo_stability_pct=True),
        RobustnessPolicy(min_wfo_stability_pct="60"),
        RobustnessPolicy(max_ruin_rate_pct=False),
        RobustnessPolicy(max_ruin_rate_pct="0"),
        RobustnessPolicy(max_monte_carlo_drawdown=True),
        RobustnessPolicy(max_monte_carlo_drawdown="100"),
    ],
)
def test_policy_rejects_boolean_and_coercible_string_thresholds(policy):
    with pytest.raises(ValueError):
        policy.validate()


@pytest.mark.parametrize(
    "policy",
    [
        RobustnessPolicy(min_wfo_stability_pct=float("nan")),
        RobustnessPolicy(min_wfo_stability_pct=float("inf")),
        RobustnessPolicy(max_ruin_rate_pct=float("nan")),
        RobustnessPolicy(max_ruin_rate_pct=float("inf")),
        RobustnessPolicy(max_monte_carlo_drawdown=float("nan")),
        RobustnessPolicy(max_monte_carlo_drawdown=float("-inf")),
    ],
)
def test_policy_rejects_nonfinite_thresholds(policy):
    with pytest.raises(ValueError):
        policy.validate()


def test_policy_allows_positive_infinite_drawdown_ceiling():
    RobustnessPolicy(max_monte_carlo_drawdown=float("inf")).validate()


def test_policy_allows_finite_integer_thresholds():
    RobustnessPolicy(
        min_wfo_stability_pct=60,
        max_ruin_rate_pct=0,
        max_monte_carlo_drawdown=500,
    ).validate()
