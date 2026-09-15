from datetime import datetime, timedelta

from core.backtest_engine import BacktestResult, BacktestStats, BacktestTrade
from core.enums import Direction
from research.evidence_gate import EvidenceGatePolicy
from research.evidence_pipeline import run_evidence_pipeline


def _result(pnl: float) -> BacktestResult:
    now = datetime(2026, 1, 1)
    trade = BacktestTrade(
        now,
        now + timedelta(minutes=1),
        now + timedelta(minutes=2),
        Direction.BUY,
        100.0,
        100.0 + pnl,
        1.0,
        pnl,
        0.0,
        pnl,
        "TP3" if pnl > 0 else "SL",
    )
    stats = BacktestStats(
        10000.0,
        10000.0 + pnl,
        pnl,
        pnl / 10000.0 * 100.0,
        1,
        int(pnl > 0),
        int(pnl < 0),
        100.0 if pnl > 0 else 0.0,
        float("inf") if pnl > 0 else 0.0,
        pnl,
        max(-pnl, 0.0),
        max(-pnl, 0.0) / 10000.0 * 100.0,
        0.0,
    )
    return BacktestResult((trade,), (10000.0, 10000.0 + pnl), stats)


def test_pipeline_composes_wfo_monte_carlo_report_and_gate():
    def evaluator(rows, params):
        return _result(float(len(rows)) * params["mult"])

    result = run_evidence_pipeline(
        list(range(9)),
        ({"mult": 1.0}, {"mult": 2.0}),
        evaluator,
        train_size=4,
        test_size=2,
        purge_size=1,
        starting_equity=10000.0,
        step=2,
        simulations=25,
        policy=EvidenceGatePolicy(min_oos_trades=2, min_expectancy=0.0),
    )

    assert len(result.wfo.oos_results) == 2
    assert result.robustness.oos_trade_count == 2
    assert result.report.oos_trade_count == 2
    assert result.report.simulations == 25
    assert result.gate.passed is True
    assert result.gate.failures == ()


def test_pipeline_gate_remains_fail_closed_for_insufficient_oos_trades():
    def evaluator(rows, params):
        return _result(1.0)

    result = run_evidence_pipeline(
        list(range(8)),
        ({"mult": 1.0},),
        evaluator,
        train_size=3,
        test_size=2,
        purge_size=1,
        starting_equity=10000.0,
        simulations=10,
        policy=EvidenceGatePolicy(min_oos_trades=3),
    )

    assert result.gate.passed is False
    assert "OOS trade count below minimum" in result.gate.failures
