"""Validated dataset entry point for SHREEK V5.2 research.

The runner deliberately stops at the research boundary: it validates the
input dataset and invokes the existing evidence pipeline. It has no network,
broker, credential, or execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, replace
from datetime import timedelta, tzinfo
from math import isclose, isfinite
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.research_certification import ResearchCertificationPolicy
from research.backtest_wfo import BacktestEvaluator, ContextBacktestEvaluator
from research.backtest_breakout_retest import run_breakout_retest_backtest
from research.breakout_retest import BreakoutRetestConfig, ResearchBar
from research.csv_adapter import load_ohlcv_csv
from research.dataset_provenance import DatasetProvenance, fingerprint_bars
from research.data_validation import MarketDataValidation, validate_market_data
from research.evidence_gate import EvidenceGatePolicy
from research.evidence_pipeline import EvidencePipelineResult, run_evidence_pipeline
from research.research_run_artifact import ResearchRunArtifact, build_research_run_artifact
from research.xauusd_source_manifest import XAUUSDSourceManifest


MANIFEST_BOUND_COST_APPLICATION_ID = "manifest-bound-breakout-retest-v1"
MANIFEST_BOUND_CONTEXT_EVALUATOR_ID = "manifest-bound-breakout-retest-context-v1"
_SIGNAL_PARAMETER_NAMES = frozenset(field.name for field in fields(BreakoutRetestConfig))
_ECONOMIC_PARAMETER_NAMES = frozenset({
    "pip_size", "volume", "spread", "slippage", "point_value",
    "commission_per_volume", "timeframe", "signal",
})


@dataclass(frozen=True)
class DatasetResearchResult:
    """Validated input evidence plus deterministic dataset provenance."""

    validation: MarketDataValidation
    provenance: DatasetProvenance
    evidence: EvidencePipelineResult
    artifact: ResearchRunArtifact


def _manifest_metadata(manifest: XAUUSDSourceManifest) -> dict[str, str]:
    """Return safe, non-account metadata bound into the research artifact."""
    return {
        "source_broker": manifest.broker.strip(),
        "source_server": manifest.server.strip(),
        "source_symbol": manifest.symbol.strip().upper(),
        "source_timezone_offset_minutes": str(manifest.timezone_offset_minutes),
        "source_digits": str(manifest.digits),
        "source_point_size": f"{manifest.point_size:.12g}",
        "source_contract_size": f"{manifest.contract_size:.12g}",
        "source_minimum_volume": f"{manifest.minimum_volume:.12g}",
        "source_volume_step": f"{manifest.volume_step:.12g}",
        "source_spread_points": f"{manifest.observed_spread_points:.12g}",
        "source_slippage_points": f"{manifest.slippage_points:.12g}",
        "source_round_turn_commission_per_lot": f"{manifest.round_turn_commission_per_lot:.12g}",
    }


def _merge_manifest_metadata(
    metadata: Mapping[str, str] | None, manifest: XAUUSDSourceManifest | None
) -> Mapping[str, str] | None:
    if manifest is None:
        return metadata
    manifest.validate()
    merged = dict(metadata or {})
    for key, value in _manifest_metadata(manifest).items():
        if key in merged and merged[key] != value:
            raise ValueError(f"artifact metadata conflicts with source manifest: {key}")
        merged[key] = value
    return merged


def run_dataset_research(
    bars: Sequence[ResearchBar],
    parameter_sets: Sequence[Mapping[str, Any]],
    evaluator: BacktestEvaluator,
    *,
    max_gap: timedelta | None = None,
    train_size: int,
    test_size: int,
    purge_size: int,
    starting_equity: float,
    step: int | None = None,
    maximize: bool = True,
    simulations: int = 1000,
    seed: int | None = 42,
    slippage_multiplier: float = 1.0,
    spread_multiplier: float = 1.0,
    policy: EvidenceGatePolicy = EvidenceGatePolicy(),
    confidence: float = 0.95,
    bootstrap_block_size: int = 2,
    bootstrap_simulations: int = 2000,
    label_horizon: int = 0,
    certification_policy: ResearchCertificationPolicy = ResearchCertificationPolicy(),
    context_size: int = 0,
    context_evaluator: ContextBacktestEvaluator | None = None,
    context_evaluator_id: str | None = None,
    artifact_metadata: Mapping[str, str] | None = None,
    source_manifest: XAUUSDSourceManifest | None = None,
) -> DatasetResearchResult:
    """Validate, fingerprint, research, and package one deterministic run."""
    validation = validate_market_data(bars, max_gap=max_gap)
    if source_manifest is not None:
        if not isinstance(source_manifest, XAUUSDSourceManifest):
            raise ValueError("source_manifest must be an XAUUSDSourceManifest")
        source_manifest.validate_bars_timezone(bars)
    provenance = fingerprint_bars(bars, validation)
    evidence = run_evidence_pipeline(
        bars,
        parameter_sets,
        evaluator,
        train_size=train_size,
        test_size=test_size,
        purge_size=purge_size,
        starting_equity=starting_equity,
        step=step,
        maximize=maximize,
        simulations=simulations,
        seed=seed,
        slippage_multiplier=slippage_multiplier,
        spread_multiplier=spread_multiplier,
        policy=policy,
        confidence=confidence,
        bootstrap_block_size=bootstrap_block_size,
        bootstrap_simulations=bootstrap_simulations,
        label_horizon=label_horizon,
        certification_policy=certification_policy,
        context_size=context_size,
        context_evaluator=context_evaluator,
        context_evaluator_id=context_evaluator_id,
    )
    artifact = build_research_run_artifact(
        evidence, provenance,
        metadata=_merge_manifest_metadata(artifact_metadata, source_manifest),
    )
    return DatasetResearchResult(validation, provenance, evidence, artifact)


def _validate_manifest_volume(manifest: XAUUSDSourceManifest, volume: float) -> float:
    if type(volume) not in (int, float) or not isfinite(float(volume)):
        raise ValueError("volume must be a finite number")
    resolved = float(volume)
    if resolved < manifest.minimum_volume:
        raise ValueError("volume must not be below the source minimum volume")
    steps = (resolved - manifest.minimum_volume) / manifest.volume_step
    if not isclose(steps, round(steps), rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("volume must align with the source volume step")
    return resolved


def _signal_config(parameters: Mapping[str, Any]) -> BreakoutRetestConfig:
    if not isinstance(parameters, Mapping):
        raise ValueError("each parameter set must be a mapping")
    names = set(parameters)
    forbidden = names & _ECONOMIC_PARAMETER_NAMES
    if forbidden:
        raise ValueError(
            "manifest-bound parameter sets cannot override execution economics: "
            + ", ".join(sorted(forbidden))
        )
    unknown = names - _SIGNAL_PARAMETER_NAMES
    if unknown:
        raise ValueError("unknown breakout-retest parameters: " + ", ".join(sorted(unknown)))
    config = BreakoutRetestConfig(**dict(parameters))
    config.validate()
    return config


def run_xauusd_breakout_retest_research(
    bars: Sequence[ResearchBar],
    parameter_sets: Sequence[Mapping[str, Any]],
    *,
    source_manifest: XAUUSDSourceManifest,
    pip_size: float,
    volume: float = 1.0,
    artifact_metadata: Mapping[str, str] | None = None,
    **kwargs: Any,
) -> DatasetResearchResult:
    """Run the canonical XAUUSD study with manifest-locked execution costs.

    Candidate parameters may tune signal thresholds only. Spread, slippage,
    point value, commission, volume, pip size, and timeframe are constructed
    outside the optimization surface so documented costs cannot be archived
    without also being consumed by the backtest engine.
    """
    if not isinstance(source_manifest, XAUUSDSourceManifest):
        raise ValueError("source_manifest must be an XAUUSDSourceManifest")
    source_manifest.validate()
    resolved_volume = _validate_manifest_volume(source_manifest, volume)
    signal_configs = tuple(_signal_config(params) for params in parameter_sets)
    if not signal_configs:
        raise ValueError("parameter_sets must be non-empty")
    base_config = source_manifest.to_breakout_retest_config(
        pip_size=pip_size,
        volume=resolved_volume,
    )

    normalized_parameters = tuple(
        {field.name: getattr(config, field.name) for field in fields(BreakoutRetestConfig)}
        for config in signal_configs
    )

    def evaluator(rows: Sequence[ResearchBar], params: Mapping[str, Any]):
        signal = _signal_config(params)
        return run_breakout_retest_backtest(rows, replace(base_config, signal=signal))

    def context_evaluator(
        rows: Sequence[ResearchBar], params: Mapping[str, Any], oos_start_index: int
    ):
        signal = _signal_config(params)
        return run_breakout_retest_backtest(
            rows,
            replace(base_config, signal=signal),
            min_signal_index=oos_start_index,
            execution_end_index=len(rows) - 1,
        )

    # Enough causal history for the longest candidate's consolidation,
    # volume baseline, retest horizon, and a preceding engulfing candle.
    context_size = max(
        config.volume_lookback
        + config.consolidation_bars
        + config.retest_max_bars
        + 2
        for config in signal_configs
    )
    forbidden_controls = {
        "context_size", "context_evaluator", "context_evaluator_id", "source_manifest"
    }
    conflicts = forbidden_controls & set(kwargs)
    if conflicts:
        raise ValueError(
            "manifest-bound runner controls causal context internally: "
            + ", ".join(sorted(conflicts))
        )

    metadata = dict(artifact_metadata or {})
    existing = metadata.get("cost_application_id")
    if existing is not None and existing != MANIFEST_BOUND_COST_APPLICATION_ID:
        raise ValueError("artifact metadata conflicts with manifest-bound cost application")
    metadata["cost_application_id"] = MANIFEST_BOUND_COST_APPLICATION_ID
    return run_dataset_research(
        bars,
        normalized_parameters,
        evaluator,
        source_manifest=source_manifest,
        artifact_metadata=metadata,
        context_size=context_size,
        context_evaluator=context_evaluator,
        context_evaluator_id=MANIFEST_BOUND_CONTEXT_EVALUATOR_ID,
        **kwargs,
    )


def run_csv_research(
    path: str | Path,
    parameter_sets: Sequence[Mapping[str, Any]],
    evaluator: BacktestEvaluator,
    *,
    assume_timezone: tzinfo | None = None,
    source_manifest: XAUUSDSourceManifest | None = None,
    **kwargs: Any,
) -> DatasetResearchResult:
    """Load a local CSV through the strict adapter, then run research.

    Naive broker timestamps are accepted only when the caller supplies an
    explicit timezone. The runner never guesses a broker/server timezone.
    """
    csv_path = Path(path)
    if not csv_path.is_file():
        raise ValueError("CSV path must reference an existing file")
    try:
        text = csv_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError("unable to read CSV dataset") from exc
    bars, _ = load_ohlcv_csv(text, assume_timezone=assume_timezone)
    return run_dataset_research(
        bars, parameter_sets, evaluator,
        source_manifest=source_manifest,
        **kwargs,
    )
