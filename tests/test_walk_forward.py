from core.walk_forward import rolling_windows, run_walk_forward


def test_rolling_windows_are_causal_and_ordered():
    windows = rolling_windows(20, 8, 4)
    assert windows[0].train_start == 0
    assert windows[0].train_end == windows[0].test_start
    assert windows[0].test_end == 12
    assert all(a.test_end <= b.test_start for a, b in zip(windows, windows[1:]))


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


def test_walk_forward_rejects_insufficient_data():
    try:
        rolling_windows(5, 4, 2)
    except ValueError as exc:
        assert "insufficient" in str(exc)
    else:
        raise AssertionError("expected insufficient-data failure")
