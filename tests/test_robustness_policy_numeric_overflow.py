import pytest

from core.robustness import RobustnessPolicy


@pytest.mark.parametrize(
    "policy",
    [
        RobustnessPolicy(min_wfo_stability_pct=10**1000),
        RobustnessPolicy(max_ruin_rate_pct=10**1000),
    ],
)
def test_policy_rejects_oversized_integer_thresholds_cleanly(policy):
    with pytest.raises(ValueError):
        policy.validate()
