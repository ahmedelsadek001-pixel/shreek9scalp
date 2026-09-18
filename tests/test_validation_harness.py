import json
import pytest
from hashlib import sha256
from datetime import datetime, timedelta

from core.backtest_engine import BacktestResult, BacktestStats, BacktestTrade
from core.enums import Direction
from research.evidence_gate import EvidenceGatePolicy
from research.validation_harness import (
    ResearchValidationResult,
    assert_reproducible,
    run_research_validation,
)


def _backtest_result(rows):
    now = datetime(2026, 1, 1)
    pnl = float(sum(rows))
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
        "TP3",
    )
    stats = BacktestStats(
        10000.0,
        10000.0 + pnl,
        pnl,
        pnl / 100.0,
        1,
        int(pnl > 0),
        int(pnl < 0),
        100.0 if pnl > 0 else 0.0,
        float("inf") if pnl > 0 else 0.0,
        pnl,
        max(-pnl, 0.0),
        max(-pnl, 0.0) / 100.0,
        0.0,
    )
    return BacktestResult((trade,), (10000.0, 10000.0 + pnl), stats)


def _run(**overrides):
    def fingerprint(rows):
        payload = json.dumps(list(rows), separators=(",", ":"), sort_keys=True).encode()
        return sha256(payload).hexdigest()

    args = dict(
        data=list(range(1, 9)),
        parameter_sets=({"x": 1},),
        evaluator=lambda rows, params: _backtest_result(rows),
        data_manifest={"dataset": "fixture", "bars": 8},
        config_manifest={"strategy": "breakout_retest", "version": 1},
        code_revision="test-revision",
        data_fingerprint_fn=fingerprint,
        evaluator_revision="fixture-evaluator-v1",
        objective_revision="fixture-objective-v1",
        dataset_id="fixture",
        version="1",
        train_size=3,
        test_size=2,
        purge_size=1,
        step=2,
        starting_equity=10000.0,
        simulations=20,
        seed=7,
        policy=EvidenceGatePolicy(
            min_oos_trades=1,
            min_expectancy=0.0,
            min_oos_stability_pct=0.0,
            max_ruin_rate_pct=100.0,
            max_worst_drawdown=10000.0,
        ),
    )
    args.update(overrides)
    return run_research_validation(**args)


def test_validation_harness_composes_complete_chain():
    result = _run()
    assert isinstance(result, ResearchValidationResult)
    assert result.passed
    assert result.release.report.oos_trade_count == result.robustness.oos_trade_count
    assert result.evidence.provenance == result.provenance
    result.validate()


def test_validation_harness_is_reproducible_with_same_inputs():
    first = _run()
    second = _run()
    assert_reproducible(first, second)
    assert first.evidence.evidence_hash == second.evidence.evidence_hash


def test_validation_harness_binds_runtime_controls_to_provenance():
    first = _run()
    second = _run(seed=8)
    with pytest.raises(ValueError, match="provenance"):
        assert_reproducible(first, second)


def test_validation_harness_binds_manifest_changes_to_provenance():
    first = _run()
    second = _run(data_manifest={"dataset": "fixture", "bars": 9})
    with pytest.raises(ValueError, match="provenance"):
        assert_reproducible(first, second)


def test_validation_harness_binds_actual_data_when_manifest_is_unchanged():
    first = _run()
    second = _run(data=[1, 2, 3, 4, 5, 6, 7, 99])
    with pytest.raises(ValueError, match="provenance"):
        assert_reproducible(first, second)


def test_validation_harness_rejects_tampered_release_metrics():
    result = _run()
    tampered_release = type(result.release)(
        result.release.passed,
        type(result.release.report)(
            result.release.report.oos_trade_count,
            result.release.report.oos_net_pnl + 1.0,
            result.release.report.oos_expectancy,
            result.release.report.oos_stability_pct,
            result.release.report.positive_oos_windows,
            result.release.report.oos_window_count,
            result.release.report.ruin_rate_pct,
            result.release.report.median_ending_equity,
            result.release.report.worst_ending_equity,
            result.release.report.median_max_drawdown,
            result.release.report.worst_max_drawdown,
            result.release.report.simulations,
        ),
        result.release.failures,
    )
    tampered = ResearchValidationResult(
        result.provenance, result.wfo, result.robustness,
        tampered_release, result.evidence,
    )
    with pytest.raises(ValueError, match="net P&L"):
        tampered.validate()


def test_validation_harness_rejects_tampered_evidence():
    result = _run()
    tampered = ResearchValidationResult(
        result.provenance,
        result.wfo,
        result.robustness,
        result.release,
        type(result.evidence)(
            result.evidence.dataset_id,
            result.evidence.version,
            result.evidence.samples,
            result.evidence.metrics,
            "0" * 64,
            result.evidence.provenance,
        ),
    )
    with pytest.raises(ValueError, match="integrity"):
        tampered.validate()


@pytest.mark.parametrize(
    "override, label",
    [
        ({"evaluator_revision": "fixture-evaluator-v2"}, "provenance"),
        ({"objective_revision": "fixture-objective-v2"}, "provenance"),
        ({"code_revision": "test-revision-v2"}, "provenance"),
        ({"parameter_sets": ({"x": 2},)}, "provenance"),
        ({"train_size": 2}, "provenance"),
        ({"test_size": 1}, "provenance"),
        ({"purge_size": 0}, "provenance"),
        ({"step": 3}, "provenance"),
        ({"policy": EvidenceGatePolicy(min_oos_trades=2, min_expectancy=0.0, min_oos_stability_pct=0.0, max_ruin_rate_pct=100.0, max_worst_drawdown=10000.0)}, "provenance"),
    ],
)
def test_validation_harness_identity_changes_when_validation_contract_changes(override, label):
    first = _run()
    second = _run(**override)
    with pytest.raises(ValueError, match=label):
        assert_reproducible(first, second)


def test_validation_harness_rejects_invalid_evaluator_revision():
    with pytest.raises(ValueError, match="evaluator_revision"):
        _run(evaluator_revision="")


def test_validation_harness_rejects_objective_revision_without_identity():
    with pytest.raises(ValueError, match="objective_revision"):
        _run(objective_revision="")


def test_validation_harness_requires_context_evaluator_identity():
    def context_evaluator(rows, params, start_index):
        return _backtest_result(rows)

    with pytest.raises(ValueError, match="context_evaluator_revision"):
        _run(context_size=1, context_evaluator=context_evaluator)


def test_validation_harness_rejects_context_size_without_context_evaluator():
    with pytest.raises(ValueError, match="context_evaluator"):
        _run(context_size=1)
