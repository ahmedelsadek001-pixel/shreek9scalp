import pytest

from core.block_bootstrap import moving_block_bootstrap


def test_block_bootstrap_is_deterministic_and_positive_for_constant_edge():
    first = moving_block_bootstrap([2.0, 2.0, 2.0, 2.0], block_size=2, simulations=100, seed=7)
    second = moving_block_bootstrap([2.0, 2.0, 2.0, 2.0], block_size=2, simulations=100, seed=7)
    assert first == second
    assert first.lower_mean == pytest.approx(2.0)
    assert first.upper_mean == pytest.approx(2.0)
    assert first.non_positive_mean_rate_pct == 0.0


def test_block_bootstrap_retains_contiguous_dependence_and_reports_uncertainty():
    summary = moving_block_bootstrap([4.0, 4.0, -4.0, -4.0], block_size=2, simulations=500, seed=11)
    assert summary.observed_mean == pytest.approx(0.0)
    assert summary.lower_mean <= 0.0 <= summary.upper_mean
    assert summary.non_positive_mean_rate_pct > 0.0


@pytest.mark.parametrize("block_size", [0, -1, 5, True])
def test_invalid_block_size_fails_closed(block_size):
    with pytest.raises(ValueError):
        moving_block_bootstrap([1.0, 2.0, 3.0, 4.0], block_size=block_size)


@pytest.mark.parametrize("simulations", [0, 1, -1, True])
def test_invalid_simulations_fail_closed(simulations):
    with pytest.raises(ValueError):
        moving_block_bootstrap([1.0, 2.0], block_size=1, simulations=simulations)


@pytest.mark.parametrize("values", [[], [1.0], [1.0, float("nan")], [1.0, float("inf")], [1.0, True]])
def test_invalid_samples_fail_closed(values):
    with pytest.raises(ValueError):
        moving_block_bootstrap(values, block_size=1)


def test_invalid_seed_fails_closed():
    with pytest.raises(ValueError):
        moving_block_bootstrap([1.0, 2.0], block_size=1, seed=True)
