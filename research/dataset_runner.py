"""Validated dataset entry point for SHREEK V5.2 research.

The runner deliberately stops at the research boundary: it validates the
input dataset and invokes the existing evidence pipeline. It has no network,
broker, credential, or execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from research.backtest_wfo import BacktestEvaluator
from research.breakout_retest import ResearchBar
from research.csv_adapter import load_ohlcv_csv
from research.dataset_consistency import DatasetConsistency, compare_overlapping_datasets
from research.dataset_provenance import DatasetProvenance, fingerprint_bars
from research.data_validation import MarketDataValidation, validate_market_data
from research.evidence_gate import EvidenceGatePolicy
from research.evidence_pipeline import EvidencePipelineResult, run_evidence_pipeline


@dataclass(frozen=True)
class DatasetResearchResult:
    """Validated input evidence plus deterministic dataset provenance."""

    validation: MarketDataValidation
    provenance: DatasetProvenance
    evidence: EvidencePipelineResult
    consistency_checks: tuple[DatasetConsistency, ...] = ()
    minimum_history_seconds: float | None = None
    max_gap_seconds: float | None = None


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
    comparison_datasets: Sequence[Sequence[ResearchBar]] = (),
    comparison_minimum_common_timestamps: int = 100,
    comparison_max_median_difference_pct: float = 0.5,
    comparison_max_p95_difference_pct: float = 1.0,
    minimum_history: timedelta | None = None,
) -> DatasetResearchResult:
    """Validate and fingerprint bars before running research evidence."""
    validation = validate_market_data(bars, max_gap=max_gap)
    if minimum_history is not None and (
        not isinstance(minimum_history, timedelta) or minimum_history <= timedelta(0)
    ):
        raise ValueError("minimum_history must be a positive timedelta or None")
    minimum_history_seconds = (
        minimum_history.total_seconds() if minimum_history is not None else None
    )
    history_seconds = (
        validation.last_timestamp.astimezone(timezone.utc)
        - validation.first_timestamp.astimezone(timezone.utc)
    ).total_seconds()
    if minimum_history_seconds is not None and history_seconds < minimum_history_seconds:
        raise ValueError(
            "research halted: dataset history is shorter than required "
            f"(actual_seconds={history_seconds}, required_seconds={minimum_history_seconds})"
        )
    consistency_checks = tuple(
        compare_overlapping_datasets(
            bars,
            comparison,
            minimum_common_timestamps=comparison_minimum_common_timestamps,
            max_median_difference_pct=comparison_max_median_difference_pct,
            max_p95_difference_pct=comparison_max_p95_difference_pct,
        )
        for comparison in comparison_datasets
    )
    if any(not check.consistent for check in consistency_checks):
        failed = next(check for check in consistency_checks if not check.consistent)
        raise ValueError(
            "research halted: cross-dataset consistency check failed "
            f"(common={failed.common_timestamps}, "
            f"median_pct={failed.median_difference_pct}, "
            f"p95_pct={failed.p95_difference_pct})"
        )
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
    )
    return DatasetResearchResult(
        validation,
        provenance,
        evidence,
        consistency_checks,
        minimum_history_seconds,
        max_gap.total_seconds() if max_gap is not None else None,
    )


def run_csv_research(
    path: str | Path,
    parameter_sets: Sequence[Mapping[str, Any]],
    evaluator: BacktestEvaluator,
    *,
    reference_csv_paths: Sequence[str | Path] = (),
    **kwargs: Any,
) -> DatasetResearchResult:
    """Load a local CSV through the strict adapter, then run research."""
    csv_path = Path(path)
    if not csv_path.is_file():
        raise ValueError("CSV path must reference an existing file")
    try:
        text = csv_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError("unable to read CSV dataset") from exc
    bars, _ = load_ohlcv_csv(text)
    reference_bars: list[tuple[ResearchBar, ...]] = []
    for reference_path in reference_csv_paths:
        reference = Path(reference_path)
        if not reference.is_file():
            raise ValueError("reference CSV path must reference an existing file")
        try:
            reference_text = reference.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ValueError("unable to read reference CSV dataset") from exc
        reference_rows, _ = load_ohlcv_csv(reference_text)
        reference_bars.append(reference_rows)
    return run_dataset_research(
        bars,
        parameter_sets,
        evaluator,
        comparison_datasets=tuple(reference_bars),
        **kwargs,
    )
