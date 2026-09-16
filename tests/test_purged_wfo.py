import pytest

from research.purged_wfo import build_purged_windows, run_purged_wfo


def test_windows_have_embargo_gap():
    windows = build_purged_windows(40, train_size=10, test_size=5, purge_size=3, step=5)
    assert windows[0].train_end == 10
    assert windows[0].purge_start == 10
    assert windows[0].purge_end == 13
    assert windows[0].test_start == 13
    assert windows[0].test_end == 18


def test_every_window_has_disjoint_train_purge_test_regions():
    windows = build_purged_windows(50, train_size=12, test_size=6, purge_size=4, step=6)
    assert windows
    for window in windows:
        assert 0 <= window.train_start < window.train_end
        assert window.train_end == window.purge_start
        assert window.purge_start < window.purge_end
        assert window.purge_end == window.test_start
        assert window.test_start < window.test_end
        assert window.train_end <= window.purge_start <= window.purge_end <= window.test_start
        assert window.train_end <= window.test_start
        assert set(range(window.train_start, window.train_end)).isdisjoint(
            range(window.test_start, window.test_end)
        )
        assert len(range(window.purge_start, window.purge_end)) == 4


def test_windows_move_forward_without_oos_overlap():
    windows = build_purged_windows(80, train_size=10, test_size=5, purge_size=3, step=7)
    assert all(later.train_start > earlier.train_start for earlier, later in zip(windows, windows[1:]))
    assert all(earlier.test_end <= later.test_start for earlier, later in zip(windows, windows[1:]))


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


def test_invalid_inputs_fail_closed():
    with pytest.raises(ValueError):
        build_purged_windows(10, 5, 5, 1)
    with pytest.raises(ValueError):
        build_purged_windows(20, 5, 5, -1)
    with pytest.raises(ValueError, match="step must be at least test_size"):
        build_purged_windows(30, 10, 5, 2, step=4)
    with pytest.raises(ValueError):
        run_purged_wfo([1, 2, 3], [], lambda values, params: 1.0, train_size=1, test_size=1, purge_size=0)
