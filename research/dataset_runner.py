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


@dataclass(frozen=True)
class DatasetResearchResult:
    """Validated input evidence plus deterministic dataset provenance."""

    validation: MarketDataValidation
    provenance: DatasetProvenance
    evidence: EvidencePipelineResult
    artifact: ResearchRunArtifact


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
) -> DatasetResearchResult:
    """Validate, fingerprint, research, and package one deterministic run."""
    validation = validate_market_data(bars, max_gap=max_gap)
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
        evidence, provenance, metadata=artifact_metadata
    )
    return DatasetResearchResult(validation, provenance, evidence, artifact)


def run_csv_research(
    path: str | Path,
    parameter_sets: Sequence[Mapping[str, Any]],
    evaluator: BacktestEvaluator,
    *,
    assume_timezone: tzinfo | None = None,
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
    return run_dataset_research(bars, parameter_sets, evaluator, **kwargs)
