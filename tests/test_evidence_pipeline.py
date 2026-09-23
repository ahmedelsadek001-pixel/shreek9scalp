from dataclasses import replace
from datetime import datetime, timedelta, timezone

from core.backtest_engine import BacktestResult, BacktestStats, BacktestTrade
from core.enums import Direction
from core.research_certification import ResearchCertificationPolicy
from research.dataset_provenance import DatasetProvenance
from research.evidence_export import build_evidence_export
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
        bootstrap_block_size=1,
        bootstrap_simulations=25,
        certification_policy=ResearchCertificationPolicy(
            min_oos_trades=2,
            min_oos_windows=2,
        ),
    )

    assert len(result.wfo.oos_results) == 2
    assert result.robustness.oos_trade_count == 2
    assert result.report.oos_trade_count == 2
    assert result.report.simulations == 25
    assert result.gate.passed is True
    assert result.gate.failures == ()
    assert result.interval.samples == 2
    assert result.bootstrap.samples == 2
    assert result.certification.passed is True


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
        bootstrap_block_size=1,
        bootstrap_simulations=10,
        certification_policy=ResearchCertificationPolicy(
            min_oos_trades=3,
            min_oos_windows=1,
        ),
    )

    assert result.gate.passed is False
    assert "OOS trade count below minimum" in result.gate.failures
    assert result.certification.passed is False
    assert "insufficient OOS trades" in result.certification.failures


def _provenance():
    return DatasetProvenance(
        "1",
        "a" * 64,
        9,
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 1, 0, 40, tzinfo=timezone.utc),
    )


def _pipeline_for_export(parameter_sets=None):
    def evaluator(rows, params):
        return _result(float(len(rows)) * params["mult"])

    return run_evidence_pipeline(
        list(range(9)),
        parameter_sets or ({"mult": 1.0}, {"mult": 2.0}),
        evaluator,
        train_size=4,
        test_size=2,
        purge_size=1,
        starting_equity=10000.0,
        step=2,
        simulations=25,
        policy=EvidenceGatePolicy(min_oos_trades=2, min_expectancy=0.0),
        bootstrap_block_size=1,
        bootstrap_simulations=25,
        certification_policy=ResearchCertificationPolicy(
            min_oos_trades=2,
            min_oos_windows=2,
        ),
    )


def test_export_archives_exact_wfo_windows_scores_and_selected_parameters():
    payload = build_evidence_export(_pipeline_for_export(), _provenance())
    wfo = payload["wfo_evidence"]
    assert len(wfo["windows"]) == 2
    assert wfo["windows"][0] == {
        "train_start": 0,
        "train_end": 4,
        "purge_start": 4,
        "purge_end": 5,
        "test_start": 5,
        "test_end": 7,
    }
    assert wfo["selected_parameters"] == [{"mult": 2.0}, {"mult": 2.0}]
    assert len(wfo["train_scores"]) == len(wfo["test_scores"]) == 2


def test_export_rejects_wfo_cardinality_mismatch():
    result = _pipeline_for_export()
    validation = replace(
        result.wfo.validation,
        selected_parameters=result.wfo.validation.selected_parameters[:-1],
    )
    forged = replace(result, wfo=replace(result.wfo, validation=validation))
    import pytest
    with pytest.raises(ValueError, match="WFO evidence cardinality"):
        build_evidence_export(forged, _provenance())


def test_export_rejects_non_json_selected_parameters():
    result = _pipeline_for_export(({"mult": 2.0, "opaque": object()},))
    import pytest
    with pytest.raises(ValueError, match="strict JSON"):
        build_evidence_export(result, _provenance())
