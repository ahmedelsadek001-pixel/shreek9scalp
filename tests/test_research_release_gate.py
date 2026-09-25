from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from core.backtest_engine import BacktestResult, BacktestStats, BacktestTrade
from core.enums import Direction
from core.promotion_gate import evaluate_v53_promotion
from core.research_certification import ResearchCertificationPolicy
from execution.safety_gate import ExecutionSafetyEvidence
from research.breakout_retest import ResearchBar
from research.dataset_provenance import DatasetProvenance
from research.dataset_runner import (
    MANIFEST_BOUND_CONTEXT_EVALUATOR_ID,
    MANIFEST_BOUND_COST_APPLICATION_ID,
    XAUUSD_THREE_TIMEFRAME_QUALITY_GATE_ID,
    run_dataset_research,
)
from research.evidence_gate import EvidenceGatePolicy, EvidenceGateResult
from research.evidence_pipeline import EvidencePipelineResult
from research.evidence_report import OOSEvidenceReport
from research.research_run_artifact import build_research_run_artifact
from research.xauusd_source_manifest import XAUUSDSourceManifest

CODE_REVISION = "a" * 40

from research.research_release_gate import (
    ResearchReleaseEvidence,
    ResearchReleasePackage,
    evaluate_research_release,
    evaluate_research_release_package,
)


def complete():
    return ResearchReleaseEvidence(True, True, True, True, True, True, True, True, True, True, True, True)


def test_complete_research_evidence_is_ready():
    result = evaluate_research_release(complete())
    assert result.ready is True
    assert result.failures == ()


def test_missing_research_evidence_blocks():
    evidence = ResearchReleaseEvidence(True, True, True, True, False, True, True, True, True, True, True, True)
    result = evaluate_research_release(evidence)
    assert result.ready is False
    assert "purged walk-forward validation is not validated" in result.failures


def test_missing_bootstrap_evidence_blocks():
    evidence = ResearchReleaseEvidence(True, True, True, True, True, True, False, True, True, True, True, True)
    result = evaluate_research_release(evidence)
    assert result.ready is False
    assert "bootstrap expectancy validation is not validated" in result.failures


def test_non_boolean_research_evidence_fails_closed():
    with pytest.raises(TypeError):
        evaluate_research_release("bad")


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("dataset_provenance_validated", "dataset provenance is not validated"),
        ("reproducible_artifact_validated", "reproducible research artifact is not validated"),
        ("strategy_version_bound", "research artifact is not bound to strategy version"),
    ],
)
def test_release_blocks_missing_reproducibility_evidence(field, message):
    evidence = complete()
    values = evidence.__dict__.copy()
    values[field] = False
    result = evaluate_research_release(ResearchReleaseEvidence(**values))
    assert result.ready is False
    assert message in result.failures


def test_legacy_release_evidence_shape_fails_closed_on_new_artifact_gates():
    evidence = ResearchReleaseEvidence(True, True, True, True, True, True, True, True, True)
    result = evaluate_research_release(evidence)
    assert result.ready is False
    assert "dataset provenance is not validated" in result.failures
    assert "reproducible research artifact is not validated" in result.failures
    assert "research artifact is not bound to strategy version" in result.failures



def _release_artifact(strategy_id="breakout-retest", strategy_version="research-v1"):
    provenance = DatasetProvenance(
        "1",
        "a" * 64,
        2,
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc),
    )
    report = OOSEvidenceReport(
        30, 100.0, 3.333333, 75.0, 3, 4, 0.0,
        10100.0, 10000.0, 50.0, 100.0, 1000,
    )
    result = EvidencePipelineResult(
        object(),
        object(),
        report,
        EvidenceGateResult(True, ()),
        EvidenceGatePolicy(),
    )
    return build_research_run_artifact(
        result,
        provenance,
        metadata={
            "strategy_id": strategy_id,
            "strategy_version": strategy_version,
            "code_revision": CODE_REVISION,
        },
    )


def _promotion_artifact(
    *, include_cost_provenance=True, adverse_cost_stress=True,
    bound_costs=True, causal_context=True, audited_sources=True,
):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars = tuple(
        ResearchBar(
            start + timedelta(minutes=5 * index),
            100.0 + index,
            101.0 + index,
            99.0 + index,
            100.5 + index,
            10.0 + index,
        )
        for index in range(13)
    )

    def build_result(rows, params, start_index=0):
        pnl = 2.0 * params["mult"]
        signal = rows[start_index].timestamp
        exit_time = rows[-1].timestamp
        trade = BacktestTrade(
            signal,
            signal,
            exit_time,
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
            1,
            0,
            100.0,
            float("inf"),
            pnl,
            0.0,
            0.0,
            0.0,
        )
        return BacktestResult((trade,), (10000.0, 10000.0 + pnl), stats)

    def evaluator(rows, params):
        return build_result(rows, params)

    def context_evaluator(rows, params, start_index):
        return build_result(rows, params, start_index)

    result = run_dataset_research(
        bars,
        ({"mult": 1.0},),
        evaluator,
        train_size=4,
        test_size=2,
        purge_size=1,
        step=2,
        starting_equity=10000.0,
        simulations=20,
        seed=7,
        slippage_multiplier=1.5 if adverse_cost_stress else 1.0,
        spread_multiplier=1.5 if adverse_cost_stress else 1.0,
        policy=EvidenceGatePolicy(
            min_oos_trades=4,
            min_expectancy=0.0,
            min_oos_stability_pct=100.0,
            max_ruin_rate_pct=0.0,
            max_worst_drawdown=100.0,
        ),
        bootstrap_block_size=1,
        bootstrap_simulations=50,
        certification_policy=ResearchCertificationPolicy(
            min_oos_trades=4,
            min_oos_windows=4,
            min_oos_stability_pct=100.0,
            max_ruin_rate_pct=0.0,
            max_oos_expectancy_degradation_pct=0.0,
            min_parameter_stability_pct=100.0,
        ),
        context_size=1 if causal_context else 0,
        context_evaluator=context_evaluator if causal_context else None,
        context_evaluator_id=(
            MANIFEST_BOUND_CONTEXT_EVALUATOR_ID if causal_context else None
        ),
        artifact_metadata={
            "strategy_id": "breakout-retest",
            "strategy_version": "research-v1",
            "code_revision": CODE_REVISION,
            **({
                "xauusd_quality_gate": XAUUSD_THREE_TIMEFRAME_QUALITY_GATE_ID,
                "xauusd_5m_source_sha256": "a" * 64,
                "xauusd_15m_source_sha256": "b" * 64,
                "xauusd_1h_source_sha256": "c" * 64,
            } if audited_sources else {}),
            **({"cost_application_id": MANIFEST_BOUND_COST_APPLICATION_ID} if bound_costs else {}),
        },
        source_manifest=(
            XAUUSDSourceManifest(
                "research-broker", "research-server", "XAUUSD", 0,
                2, 0.01, 100.0, 0.01, 0.01, 19.0, 7.0, 1.5,
            )
            if include_cost_provenance else None
        ),
    )
    return result.artifact


def test_release_package_requires_independent_source_recheck():
    package = ResearchReleasePackage(
        complete(),
        _promotion_artifact(),
        "breakout-retest",
        "research-v1",
        CODE_REVISION,
    )
    decision = evaluate_research_release_package(package)
    assert decision.ready is False
    assert decision.failures == ("research release lacks source files for independent quality recheck",)
    promotion = evaluate_v53_promotion(
        package, ExecutionSafetyEvidence(True, True, True, True, True, True, True)
    )
    assert promotion.ready is False
    assert "V5.2 promotion blocked: research release lacks source files for independent quality recheck" in promotion.failures


def test_release_package_rejects_unavailable_source_files():
    package = ResearchReleasePackage(
        complete(), _promotion_artifact(), "breakout-retest", "research-v1",
        CODE_REVISION, {"5m": "/missing/m5.csv", "15m": "/missing/m15.csv", "1h": "/missing/h1.csv"},
    )
    decision = evaluate_research_release_package(package)
    assert not decision.ready
    assert "research release source files cannot be independently verified" in decision.failures


def test_release_package_rechecks_source_hashes_and_m5_bars(monkeypatch):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars = tuple(ResearchBar(start + timedelta(minutes=5 * index), 100.0 + index,
                             101.0 + index, 99.0 + index, 100.5 + index, 10.0 + index)
                 for index in range(13))
    files = tuple(SimpleNamespace(timeframe=frame, sha256=digest * 64)
                  for frame, digest in (("5m", "a"), ("15m", "b"), ("1h", "c")))
    from research import research_release_gate

    def audited(_paths, *, source_manifest):
        assert source_manifest.symbol == "XAUUSD"
        return SimpleNamespace(quality=SimpleNamespace(passed=True), files=files), {"5m": bars}

    monkeypatch.setattr(research_release_gate, "load_and_audit_xauusd_csv_bundle", audited)
    base = ResearchReleasePackage(
        complete(), _promotion_artifact(), "breakout-retest", "research-v1",
        CODE_REVISION, {"5m": "m5", "15m": "m15", "1h": "h1"},
    )
    assert evaluate_research_release_package(base).ready is True

    files = tuple(SimpleNamespace(timeframe=frame, sha256="d" * 64 if frame == "5m" else digest * 64)
                  for frame, digest in (("5m", "a"), ("15m", "b"), ("1h", "c")))
    assert "research release source file fingerprints disagree with artifact" in (
        evaluate_research_release_package(base).failures
    )
    files = tuple(SimpleNamespace(timeframe=frame, sha256=digest * 64)
                  for frame, digest in (("5m", "a"), ("15m", "b"), ("1h", "c")))
    bars = bars[:-1]
    assert "research release M5 bars disagree with artifact dataset" in (
        evaluate_research_release_package(base).failures
    )


def test_release_package_blocks_missing_broker_cost_provenance():
    package = ResearchReleasePackage(
        complete(),
        _promotion_artifact(include_cost_provenance=False),
        "breakout-retest",
        "research-v1",
        CODE_REVISION,
    )
    decision = evaluate_research_release_package(package)
    assert decision.ready is False
    assert "research artifact lacks complete broker cost provenance" in decision.failures
    promotion = evaluate_v53_promotion(
        package, ExecutionSafetyEvidence(True, True, True, True, True, True, True)
    )
    assert promotion.ready is False
    assert "V5.2 promotion blocked: research artifact lacks complete broker cost provenance" in promotion.failures


def test_release_package_blocks_missing_three_timeframe_source_fingerprints():
    package = ResearchReleasePackage(
        complete(), _promotion_artifact(audited_sources=False),
        "breakout-retest", "research-v1", CODE_REVISION,
    )
    decision = evaluate_research_release_package(package)
    assert decision.ready is False
    assert "research artifact lacks accepted three-timeframe XAUUSD source fingerprints" in decision.failures


def test_release_package_blocks_unstressed_execution_costs():
    package = ResearchReleasePackage(
        complete(),
        _promotion_artifact(adverse_cost_stress=False),
        "breakout-retest",
        "research-v1",
        CODE_REVISION,
    )
    decision = evaluate_research_release_package(package)
    assert decision.ready is False
    assert "research artifact lacks adverse execution-cost stress" in decision.failures


def test_release_package_blocks_unbound_broker_costs():
    package = ResearchReleasePackage(
        complete(),
        _promotion_artifact(bound_costs=False),
        "breakout-retest",
        "research-v1",
        CODE_REVISION,
    )
    decision = evaluate_research_release_package(package)
    assert decision.ready is False
    assert "research artifact costs were not applied by the manifest-bound backtest" in decision.failures


def test_release_package_blocks_missing_causal_oos_context():
    package = ResearchReleasePackage(
        complete(),
        _promotion_artifact(causal_context=False),
        "breakout-retest",
        "research-v1",
        CODE_REVISION,
    )
    decision = evaluate_research_release_package(package)
    assert decision.ready is False
    assert "research artifact lacks causal manifest-bound OOS warm-up context" in decision.failures


def test_release_package_blocks_strategy_bound_but_non_empirical_artifact():
    package = ResearchReleasePackage(
        complete(),
        _release_artifact(),
        "breakout-retest",
        "research-v1",
        CODE_REVISION,
    )
    decision = evaluate_research_release_package(package)
    assert decision.ready is False
    assert "research artifact lacks reproducible WFO evidence" in decision.failures
    assert "research artifact lacks statistical certification evidence" in decision.failures


@pytest.mark.parametrize(
    ("strategy_id", "strategy_version"),
    [
        ("wrong", "research-v1"),
        ("breakout-retest", "wrong"),
    ],
)
def test_release_package_blocks_strategy_identity_mismatch(strategy_id, strategy_version):
    package = ResearchReleasePackage(
        complete(),
        _release_artifact(),
        strategy_id,
        strategy_version,
        CODE_REVISION,
    )
    decision = evaluate_research_release_package(package)
    assert decision.ready is False
    assert decision.failures == ("research artifact identity validation failed",)


@pytest.mark.parametrize(
    "code_revision",
    [
        "b" * 40,
        "A" * 40,
        "short",
    ],
)
def test_release_package_blocks_code_revision_mismatch_or_malformed(code_revision):
    package = ResearchReleasePackage(
        complete(),
        _promotion_artifact(),
        "breakout-retest",
        "research-v1",
        code_revision,
    )
    decision = evaluate_research_release_package(package)
    assert decision.ready is False
    assert decision.failures == ("research artifact identity validation failed",)
