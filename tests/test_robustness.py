from datetime import datetime, timedelta

import pytest

from core.backtest_engine import BacktestResult, BacktestStats, BacktestTrade
from core.enums import Direction
from core.robustness import RobustnessPolicy, build_robustness_report
from core.walk_forward import WalkForwardResult, WalkForwardSummary, WalkForwardWindow
from research.backtest_wfo import run_backtest_wfo
from research.robustness import run_oos_monte_carlo


def _wfo_summary(*results):
    scores = [result.test_score for result in results]
    positive = sum(score > 0 for score in scores)
    ordered = sorted(scores)
    count = len(ordered)
    median = ordered[count // 2] if count % 2 else (ordered[count // 2 - 1] + ordered[count // 2]) / 2.0
    return WalkForwardSummary(
        tuple(results),
        sum(scores) / count,
        median,
        positive,
        positive / count * 100.0,
    )


def test_robustness_report_passes_clean_inputs():
    wfo = _wfo_summary(
        WalkForwardResult(WalkForwardWindow(0, 3, 3, 5), {"x": 1}, 1.0, 1.0),
    )
    report = build_robustness_report(wfo, [10.0, -2.0, 8.0], simulations=50, seed=7)
    assert report.passed
    assert report.failures == ()


def test_robustness_report_rejects_empty_wfo_evidence():
    wfo = WalkForwardSummary((), 1.0, 1.0, 0, 100.0)
    with pytest.raises(ValueError, match="at least one window"):
        build_robustness_report(wfo, [10.0, -2.0], simulations=20, seed=7)


def test_robustness_report_rejects_invalid_wfo_boundaries():
    wfo = WalkForwardSummary(
        (WalkForwardResult(WalkForwardWindow(0, 4, 3, 5), {"x": 1}, 1.0, 1.0),),
        1.0,
        1.0,
        1,
        100.0,
    )
    with pytest.raises(ValueError, match="invalid or overlapping"):
        build_robustness_report(wfo, [10.0, -2.0], simulations=20, seed=7)


def test_robustness_report_rejects_overlapping_oos_windows():
    wfo = WalkForwardSummary(
        (
            WalkForwardResult(WalkForwardWindow(0, 3, 3, 6), {"x": 1}, 1.0, 1.0),
            WalkForwardResult(WalkForwardWindow(3, 6, 5, 8), {"x": 1}, 1.0, 1.0),
        ),
        1.0,
        1.0,
        2,
        100.0,
    )
    with pytest.raises(ValueError, match="overlapping OOS"):
        build_robustness_report(wfo, [10.0, -2.0], simulations=20, seed=7)


def test_robustness_report_rejects_non_finite_wfo_score():
    wfo = WalkForwardSummary(
        (WalkForwardResult(WalkForwardWindow(0, 3, 3, 5), {"x": 1}, 1.0, float("nan")),),
        1.0,
        1.0,
        1,
        100.0,
    )
    with pytest.raises(ValueError, match="invalid or overlapping"):
        build_robustness_report(wfo, [10.0, -2.0], simulations=20, seed=7)


def test_robustness_report_rejects_inconsistent_aggregate():
    result = WalkForwardResult(WalkForwardWindow(0, 3, 3, 5), {"x": 1}, 1.0, 2.0)
    wfo = WalkForwardSummary((result,), 999.0, 2.0, 1, 100.0)
    with pytest.raises(ValueError, match="aggregate test score"):
        build_robustness_report(wfo, [10.0, -2.0], simulations=20, seed=7)


def test_robustness_report_rejects_inconsistent_median_and_counts():
    results = (
        WalkForwardResult(WalkForwardWindow(0, 3, 3, 5), {"x": 1}, 1.0, 2.0),
        WalkForwardResult(WalkForwardWindow(5, 8, 8, 10), {"x": 1}, 1.0, -1.0),
    )
    with pytest.raises(ValueError, match="median test score"):
        build_robustness_report(WalkForwardSummary(results, 0.5, 99.0, 1, 50.0), [10.0, -2.0], simulations=20, seed=7)
    with pytest.raises(ValueError, match="positive window count"):
        build_robustness_report(WalkForwardSummary(results, 0.5, 0.5, 0, 50.0), [10.0, -2.0], simulations=20, seed=7)


def test_robustness_report_rejects_inconsistent_stability():
    result = WalkForwardResult(WalkForwardWindow(0, 3, 3, 5), {"x": 1}, 1.0, 2.0)
    wfo = WalkForwardSummary((result,), 2.0, 2.0, 1, 50.0)
    with pytest.raises(ValueError, match="stability"):
        build_robustness_report(wfo, [10.0, -2.0], simulations=20, seed=7)


def test_robustness_report_rejects_low_wfo_stability():
    result = WalkForwardResult(WalkForwardWindow(0, 3, 3, 5), {"x": 1}, -1.0, -1.0)
    wfo = _wfo_summary(result)
    policy = RobustnessPolicy(min_wfo_stability_pct=60.0)
    report = build_robustness_report(wfo, [10.0, -2.0], simulations=20, seed=7, policy=policy)
    assert not report.passed
    assert "WFO stability below minimum" in report.failures


def test_policy_rejects_invalid_thresholds():
    try:
        RobustnessPolicy(min_wfo_stability_pct=101).validate()
    except ValueError:
        pass
    else:
        raise AssertionError("expected invalid WFO threshold")


def _result(pnl_values):
    now = datetime(2026, 1, 1)
    trades = tuple(
        BacktestTrade(
            now + timedelta(minutes=index * 3),
            now + timedelta(minutes=index * 3 + 1),
            now + timedelta(minutes=index * 3 + 2),
            Direction.BUY,
            100.0,
            100.0 + pnl,
            1.0,
            pnl,
            0.0,
            pnl,
            "TP3" if pnl > 0 else "SL",
        )
        for index, pnl in enumerate(pnl_values)
    )
    net = sum(pnl_values)
    wins = sum(pnl > 0 for pnl in pnl_values)
    losses = sum(pnl < 0 for pnl in pnl_values)
    gross_profit = sum(pnl for pnl in pnl_values if pnl > 0)
    gross_loss = sum(-pnl for pnl in pnl_values if pnl < 0)
    stats = BacktestStats(
        10000.0,
        10000.0 + net,
        net,
        net / 10000.0 * 100.0,
        len(pnl_values),
        wins,
        losses,
        gross_profit,
        gross_profit / gross_loss if gross_loss else float("inf"),
        net / len(pnl_values),
        gross_loss,
        gross_loss / 10000.0 * 100.0,
        0.0,
    )
    equity = [10000.0]
    for pnl in pnl_values:
        equity.append(equity[-1] + pnl)
    return BacktestResult(trades, tuple(equity), stats)


def _wfo_result():
    data = [1, 2, 3, 4, 5, 6, 7, 8]

    def evaluator(rows, params):
        return _result((float(sum(rows) * params["mult"]),))

    return run_backtest_wfo(
        data,
        ({"mult": 1.0},),
        evaluator,
        train_size=3,
        test_size=2,
        purge_size=1,
        step=2,
    )


def test_monte_carlo_uses_actual_oos_trade_pnl():
    result = _wfo_result()
    evidence = run_oos_monte_carlo(
        result,
        starting_equity=10000.0,
        simulations=20,
        seed=7,
    )

    expected = tuple(trade.net_pnl for backtest in result.oos_results for trade in backtest.trades)
    assert evidence.oos_trade_pnl == expected
    assert evidence.oos_trade_count == len(expected)
    assert evidence.summary.simulations == 20


def test_monte_carlo_rejects_empty_oos_results():
    result = _wfo_result()
    empty = type(result)(result.validation, result.train_metrics, result.oos_metrics, ())
    with pytest.raises(ValueError, match="at least one trade"):
        run_oos_monte_carlo(empty, starting_equity=10000.0, simulations=10)


def test_monte_carlo_is_reproducible_for_same_oos_evidence():
    result = _wfo_result()
    first = run_oos_monte_carlo(result, starting_equity=10000.0, simulations=50, seed=11)
    second = run_oos_monte_carlo(result, starting_equity=10000.0, simulations=50, seed=11)
    assert first.summary == second.summary
