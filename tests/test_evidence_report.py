from datetime import datetime, timedelta

import pytest

from core.backtest_engine import BacktestResult, BacktestStats, BacktestTrade
from core.enums import Direction
from research.backtest_wfo import run_backtest_wfo
from research.evidence_report import build_oos_evidence_report
from research.robustness import run_oos_monte_carlo


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
        wins / len(pnl_values) * 100.0,
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


def _evidence():
    data = list(range(1, 9))

    def evaluator(rows, params):
        return _result((float(sum(rows) * params["mult"]),))

    wfo = run_backtest_wfo(
        data,
        ({"mult": 1.0},),
        evaluator,
        train_size=3,
        test_size=2,
        purge_size=1,
        step=2,
    )
    robustness = run_oos_monte_carlo(
        wfo,
        starting_equity=10000.0,
        simulations=25,
        seed=9,
    )
    return wfo, robustness


def test_report_is_derived_from_wfo_and_robustness():
    wfo, robustness = _evidence()
    report = build_oos_evidence_report(wfo, robustness)

    assert report.oos_trade_count == robustness.oos_trade_count
    assert report.oos_net_pnl == wfo.oos_net_pnl
    assert report.oos_expectancy == wfo.oos_expectancy
    assert report.oos_stability_pct == wfo.oos_stability_pct
    assert report.positive_oos_windows == wfo.positive_oos_windows
    assert report.oos_window_count == len(wfo.oos_metrics)
    assert report.ruin_rate_pct == robustness.summary.ruin_rate_pct
    assert report.simulations == 25


def test_report_rejects_inconsistent_robustness_type():
    wfo, _ = _evidence()
    with pytest.raises(ValueError, match="RobustnessEvidence"):
        build_oos_evidence_report(wfo, object())


def test_report_rejects_robustness_trade_pnl_tampering():
    wfo, robustness = _evidence()
    tampered = type(robustness)(
        tuple(value + 0.01 for value in robustness.oos_trade_pnl),
        robustness.starting_equity,
        robustness.summary,
    )
    with pytest.raises(ValueError, match="does not match WFO"):
        build_oos_evidence_report(wfo, tampered)
