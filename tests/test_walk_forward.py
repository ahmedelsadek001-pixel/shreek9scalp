from core.walk_forward import rolling_windows, run_walk_forward
import pytest


def test_rolling_windows_are_causal_and_ordered():
    windows = rolling_windows(20, 8, 4)
    assert windows[0].train_start == 0
    assert windows[0].train_end == windows[0].test_start
    assert windows[0].test_end == 12
    assert all(a.test_end <= b.test_start for a, b in zip(windows, windows[1:]))


def test_purged_walk_forward_leaves_embargo_between_train_and_test():
    windows = rolling_windows(24, 8, 4, step=4, purge_size=2)
    assert windows[0].train_end == 8
    assert windows[0].test_start == 10
    assert windows[0].test_end == 14
    assert all(a.test_end <= b.test_start for a, b in zip(windows, windows[1:]))


def test_overlapping_oos_step_is_rejected():
    with pytest.raises(ValueError, match="overlapping OOS"):
        rolling_windows(20, 8, 4, step=2)


def test_negative_purge_is_rejected():
    with pytest.raises(ValueError, match="purge_size"):
        rolling_windows(20, 8, 4, purge_size=-1)


def test_purge_can_make_dataset_insufficient():
    with pytest.raises(ValueError, match="insufficient"):
        rolling_windows(14, 8, 4, purge_size=3)


def test_walk_forward_selects_on_train_and_scores_out_of_sample():
    data = list(range(12))
    params = ({"mult": 1.0}, {"mult": 2.0})

    def evaluator(rows, p):
        return sum(rows) * p["mult"]

    result = run_walk_forward(data, params, evaluator, train_size=6, test_size=3, step=3)
    assert result.windows
    assert result.windows[0].parameters == {"mult": 2.0}
    assert result.positive_test_windows == len(result.windows)
    assert result.stability_pct == 100.0


def test_walk_forward_applies_purge_before_oos_evaluation():
    data = list(range(15))
    params = ({"mult": 1.0},)

    def evaluator(rows, _):
        return sum(rows)

    result = run_walk_forward(
        data, params, evaluator, train_size=5, test_size=3, step=3, purge_size=2
    )
    assert result.windows[0].window.test_start == 7
    assert result.windows[0].test_score == sum(data[7:10])


def test_walk_forward_future_mutation_cannot_change_prior_windows():
    data = list(range(24))
    mutated = data.copy()
    mutated[16:] = [10_000 + i for i in range(8)]

    def evaluator(rows, _):
        return float(sum(rows))

    baseline = run_walk_forward(data, ({"x": 1},), evaluator, 6, 3, step=3)
    changed = run_walk_forward(mutated, ({"x": 1},), evaluator, 6, 3, step=3)
    for before, after in zip(baseline.windows, changed.windows):
        if before.window.test_end <= 16:
            assert before.train_score == after.train_score
            assert before.test_score == after.test_score


def test_walk_forward_rejects_non_boolean_maximize():
    with pytest.raises(ValueError, match="maximize"):
        run_walk_forward(list(range(10)), ({"x": 1},), lambda rows, p: 1.0, 5, 2, maximize=1)


def test_walk_forward_rejects_insufficient_data():
    try:
        rolling_windows(5, 4, 2)
    except ValueError as exc:
        assert "insufficient" in str(exc)
    else:
        raise AssertionError("expected insufficient-data failure")
