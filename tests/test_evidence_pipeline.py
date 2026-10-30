from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

import pytest

from core.backtest_engine import BacktestResult, BacktestStats, BacktestTrade
from core.enums import Direction
from core.research_certification import ResearchCertificationPolicy
from research.breakout_retest import ResearchBar
from research.dataset_provenance import DatasetProvenance
from research.evidence_export import build_evidence_export
from research.evidence_gate import EvidenceGatePolicy
from research.evidence_pipeline import run_evidence_pipeline
from research.research_run_artifact import build_research_run_artifact


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


def test_pipeline_archives_and_uses_causal_warmup_context():
    seen = []

    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars = tuple(
        ResearchBar(start + timedelta(minutes=5 * index), 1.0, 1.0, 1.0, 1.0, 1.0)
        for index in range(9)
    )

    def timestamped_result(rows, start_index=0):
        base = _result(1.0)
        trade = replace(
            base.trades[0],
            signal_time=rows[start_index].timestamp,
            entry_time=rows[start_index].timestamp,
            exit_time=rows[-1].timestamp,
        )
        return replace(base, trades=(trade,))

    def evaluator(rows, params):
        return timestamped_result(rows)

    def context_evaluator(rows, params, start_index):
        seen.append((tuple(row.timestamp for row in rows), start_index))
        return timestamped_result(rows, start_index)

    result = run_evidence_pipeline(
        bars,
        ({"mult": 1.0},),
        evaluator,
        train_size=4,
        test_size=2,
        purge_size=1,
        starting_equity=10000.0,
        step=2,
        simulations=10,
        bootstrap_block_size=1,
        bootstrap_simulations=10,
        context_size=2,
        context_evaluator=context_evaluator,
        context_evaluator_id="fixture-context-v1",
        certification_policy=ResearchCertificationPolicy(
            min_oos_trades=2,
            min_oos_windows=2,
        ),
    )
    assert len(seen) == 2
    assert [item[1] for item in seen] == [2, 2]
    assert seen[0][0] == tuple(bar.timestamp for bar in bars[3:7])
    assert seen[1][0] == tuple(bar.timestamp for bar in bars[5:9])
    assert result.run_config.context_size == 2
    assert result.run_config.context_evaluator_id == "fixture-context-v1"


def test_pipeline_rejects_unidentified_warmup_context():
    with pytest.raises(ValueError, match="context_evaluator_id"):
        run_evidence_pipeline(
            list(range(8)),
            ({"mult": 1.0},),
            lambda rows, params: _result(1.0),
            train_size=3,
            test_size=2,
            purge_size=1,
            starting_equity=10000.0,
            context_size=1,
            context_evaluator=lambda rows, params, start: _result(1.0),
        )


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
    config = payload["research_config"]
    assert config["train_size"] == 4
    assert config["test_size"] == 2
    assert config["purge_size"] == 1
    assert config["step"] == 2
    assert config["objective_id"] == "expectancy"
    assert config["candidate_parameters"] == [{"mult": 1.0}, {"mult": 2.0}]
    assert config["context_size"] == 0
    assert config["context_evaluator_id"] is None


def test_export_rejects_wfo_cardinality_mismatch():
    result = _pipeline_for_export()
    validation = replace(
        result.wfo.validation,
        selected_parameters=result.wfo.validation.selected_parameters[:-1],
    )
    forged = replace(result, wfo=replace(result.wfo, validation=validation))
    with pytest.raises(ValueError, match="WFO evidence cardinality"):
        build_evidence_export(forged, _provenance())


def test_export_rejects_non_json_selected_parameters():
    result = _pipeline_for_export(({"mult": 2.0, "opaque": object()},))
    with pytest.raises(ValueError, match="strict JSON"):
        build_evidence_export(result, _provenance())


def test_custom_objective_requires_stable_objective_id():
    def evaluator(rows, params):
        return _result(1.0)

    with pytest.raises(ValueError, match="explicit objective_id"):
        run_evidence_pipeline(
            list(range(8)),
            ({"mult": 1.0},),
            evaluator,
            train_size=3,
            test_size=2,
            purge_size=1,
            starting_equity=10000.0,
            objective=lambda metrics: metrics.net_pnl,
            bootstrap_block_size=1,
            bootstrap_simulations=10,
            certification_policy=ResearchCertificationPolicy(
                min_oos_trades=2,
                min_oos_windows=1,
            ),
        )


@pytest.mark.parametrize(
    ("section", "field", "value", "message"),
    [
        ("research_config", "train_size", 5, "train size does not match"),
        ("research_config", "purge_size", 2, "purge size does not match"),
        ("research_config", "step", 3, "step does not match"),
        ("research_config", "simulations", 26, "simulations do not match"),
        ("wfo_evidence", "selected_parameters", [{"mult": 9.0}, {"mult": 9.0}], "absent from candidate grid"),
    ],
)
def test_artifact_rejects_rehashed_wfo_config_tampering(section, field, value, message):
    artifact = build_research_run_artifact(_pipeline_for_export(), _provenance())
    payload = json.loads(artifact.evidence_export)
    payload[section][field] = value
    export = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    forged = replace(
        artifact,
        evidence_export=export,
        evidence_export_sha256=sha256(export.encode("utf-8")).hexdigest(),
    )
    with pytest.raises(ValueError, match=message):
        forged.validate()


def test_artifact_rejects_rehashed_shifted_wfo_geometry_even_when_sizes_match():
    artifact = build_research_run_artifact(_pipeline_for_export(), _provenance())
    payload = json.loads(artifact.evidence_export)
    for window in payload["wfo_evidence"]["windows"]:
        for field in (
            "train_start", "train_end", "purge_start",
            "purge_end", "test_start", "test_end",
        ):
            window[field] += 1
    export = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    forged = replace(
        artifact,
        evidence_export=export,
        evidence_export_sha256=sha256(export.encode("utf-8")).hexdigest(),
    )
    with pytest.raises(ValueError, match="windows do not match dataset and research config"):
        forged.validate()


def test_artifact_rejects_rehashed_nonchronological_timestamped_training_windows():
    artifact = build_research_run_artifact(_pipeline_for_export(), _provenance())
    payload = json.loads(artifact.evidence_export)
    payload["wfo_evidence"]["window_timestamps"] = [
        {
            "train_first": "2026-01-01T00:02:00+00:00",
            "train_last": "2026-01-01T00:03:00+00:00",
            "purge_first": "2026-01-01T00:04:00+00:00",
            "purge_last": "2026-01-01T00:04:00+00:00",
            "test_first": "2026-01-01T00:05:00+00:00",
            "test_last": "2026-01-01T00:06:00+00:00",
        },
        {
            "train_first": "2026-01-01T00:01:00+00:00",
            "train_last": "2026-01-01T00:03:30+00:00",
            "purge_first": "2026-01-01T00:07:00+00:00",
            "purge_last": "2026-01-01T00:07:00+00:00",
            "test_first": "2026-01-01T00:08:00+00:00",
            "test_last": "2026-01-01T00:09:00+00:00",
        },
    ]
    export = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    forged = replace(
        artifact,
        evidence_export=export,
        evidence_export_sha256=sha256(export.encode("utf-8")).hexdigest(),
    )
    with pytest.raises(ValueError, match="timestamped training windows must be chronological"):
        forged.validate()
