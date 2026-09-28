import pytest

from research.purged_wfo import build_purged_windows, run_purged_wfo


def test_windows_have_embargo_gap():
    windows = build_purged_windows(40, train_size=10, test_size=5, purge_size=3, step=5)
    assert windows[0].train_end == 10
    assert windows[0].purge_start == 10
    assert windows[0].purge_end == 13
    assert windows[0].test_start == 13
    assert windows[0].test_end == 18


def test_oos_windows_cannot_overlap():
    with pytest.raises(ValueError, match="overlapping OOS windows"):
        build_purged_windows(40, train_size=10, test_size=5, purge_size=2, step=4)


def test_non_overlapping_oos_windows_preserve_gaps_when_step_is_larger():
    windows = build_purged_windows(50, train_size=10, test_size=5, purge_size=2, step=7)
    assert all(left.test_end <= right.test_start for left, right in zip(windows, windows[1:]))


def test_purged_wfo_selects_on_train_only():
    data = list(range(30))

    def evaluator(values, params):
        return params["bias"] + float(sum(values))

    result = run_purged_wfo(
        data,
        [{"bias": 1.0}, {"bias": 2.0}],
        evaluator,
        train_size=10,
        test_size=5,
        purge_size=2,
    )
    assert result.windows
    assert all(params["bias"] == 2.0 for params in result.selected_parameters)
    assert len(result.train_scores) == len(result.test_scores) == len(result.windows)


def test_evaluator_mutation_cannot_change_input_or_selected_parameters():
    original_params = {"bias": 2.0, "nested": {"scale": 1.0}}

    def mutating_evaluator(values, params):
        params["bias"] = -999.0
        params["nested"]["scale"] = -999.0
        return float(sum(values))

    result = run_purged_wfo(
        list(range(20)),
        [original_params],
        mutating_evaluator,
        train_size=5,
        test_size=3,
        purge_size=1,
    )

    assert original_params == {"bias": 2.0, "nested": {"scale": 1.0}}
    assert all(
        params == {"bias": 2.0, "nested": {"scale": 1.0}}
        for params in result.selected_parameters
    )


def test_invalid_inputs_fail_closed():
    with pytest.raises(ValueError):
        build_purged_windows(10, 5, 5, 1)
    with pytest.raises(ValueError):
        build_purged_windows(20, 5, 5, -1)
    with pytest.raises(ValueError, match="integers"):
        build_purged_windows(20, 5, 5, 1.5)
    with pytest.raises(ValueError):
        run_purged_wfo([1, 2, 3], [], lambda values, params: 1.0, train_size=1, test_size=1, purge_size=0)
