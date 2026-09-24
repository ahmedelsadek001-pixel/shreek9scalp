"""Validated dataset entry point for SHREEK V5.2 research.

The runner deliberately stops at the research boundary: it validates the
input dataset and invokes the existing evidence pipeline. It has no network,
broker, credential, or execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta, tzinfo
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.research_certification import ResearchCertificationPolicy
from research.backtest_wfo import BacktestEvaluator
from research.breakout_retest import ResearchBar
from research.csv_adapter import load_ohlcv_csv
from research.dataset_provenance import DatasetProvenance, fingerprint_bars
from research.data_validation import MarketDataValidation, validate_market_data
from research.evidence_gate import EvidenceGatePolicy
from research.evidence_pipeline import EvidencePipelineResult, run_evidence_pipeline
from research.research_run_artifact import ResearchRunArtifact, build_research_run_artifact
from research.xauusd_source_manifest import XAUUSDSourceManifest


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
    )
    artifact = build_research_run_artifact(
        evidence, provenance,
        metadata=_merge_manifest_metadata(artifact_metadata, source_manifest),
    )
    return DatasetResearchResult(validation, provenance, evidence, artifact)


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
