"""Validated dataset entry point for SHREEK V5.2 research.

The runner deliberately stops at the research boundary: it validates the
input dataset and invokes the existing evidence pipeline. It has no network,
broker, credential, or execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

from research.csv_adapter import load_csv
from research.data_validation import MarketDataValidation
from research.evidence_gate import EvidenceGatePolicy
from research.evidence_pipeline import EvidencePipelineResult, run_evidence_pipeline
from research.breakout_retest import ResearchBar


@dataclass(frozen=True)
class DatasetResearchResult:
    """Validated input evidence plus the complete research result."""

    validation: MarketDataValidation
    evidence: EvidencePipelineResult


def run_dataset_research(
    bars: Sequence[ResearchBar],
    parameter_sets: Sequence[Mapping[str, Any]],
    evaluator,
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
) -> DatasetResearchResult:
    """Validate bars, then execute the existing research-only evidence chain."""
    from research.data_validation import validate_market_data

    validation = validate_market_data(bars, max_gap=max_gap)
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
    )
    return DatasetResearchResult(validation, evidence)


def run_csv_research(
    path: str | Path,
    parameter_sets: Sequence[Mapping[str, Any]],
    evaluator,
    **kwargs: Any,
) -> DatasetResearchResult:
    """Load a local CSV through the strict adapter, then run research."""
    bars = load_csv(path)
    return run_dataset_research(bars, parameter_sets, evaluator, **kwargs)
