"""Fail-closed V5.2 research validation harness.

The harness composes causal WFO, realized OOS robustness, evidence gating and
provenance-bound evidence into one research-only validation result. It never
authorizes live execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Callable, Mapping, Sequence

from core.research_provenance import ResearchProvenance, build_provenance, validate_provenance
from research.backtest_wfo import (
    BacktestEvaluator,
    BacktestWFOResult,
    ContextBacktestEvaluator,
    MetricEvaluator,
    run_backtest_wfo,
)
from research.evidence_gate import (
    EvidenceGatePolicy,
    ResearchReleaseGateResult,
    evaluate_research_release,
)
from research.research_evidence import ResearchEvidence, verify_evidence
from research.robustness import RobustnessEvidence, run_oos_monte_carlo


@dataclass(frozen=True)
class ResearchValidationResult:
    """Complete immutable research validation chain; never live authority."""

    provenance: ResearchProvenance
    wfo: BacktestWFOResult
    robustness: RobustnessEvidence
    release: ResearchReleaseGateResult
    evidence: ResearchEvidence

    @property
    def passed(self) -> bool:
        return self.release.passed

    def validate(self) -> None:
        """Fail closed if any link in the validation chain is malformed."""
        validate_provenance(self.provenance)
        if not isinstance(self.wfo, BacktestWFOResult):
            raise ValueError("validation wfo must be a BacktestWFOResult")
        if not isinstance(self.robustness, RobustnessEvidence):
            raise ValueError("validation robustness must be RobustnessEvidence")
        if not isinstance(self.release, ResearchReleaseGateResult):
            raise ValueError("validation release must be a ResearchReleaseGateResult")
        if not isinstance(self.evidence, ResearchEvidence) or not verify_evidence(self.evidence):
            raise ValueError("validation evidence integrity check failed")
        if self.evidence.provenance != self.provenance:
            raise ValueError("evidence provenance does not match validation provenance")
        if self.release.report.oos_trade_count != self.robustness.oos_trade_count:
            raise ValueError("release report trade count does not match robustness evidence")
        self.robustness.validate()


def _metric_payload(
    wfo: BacktestWFOResult,
    robustness: RobustnessEvidence,
) -> dict[str, float]:
    """Build deterministic evidence metrics from the actual validation chain."""
    values = {
        "oos_trade_count": float(wfo.oos_trade_count if hasattr(wfo, "oos_trade_count") else robustness.oos_trade_count),
        "oos_net_pnl": float(wfo.oos_net_pnl),
        "oos_expectancy": float(wfo.oos_expectancy),
        "oos_stability_pct": float(wfo.oos_stability_pct),
        "positive_oos_windows": float(wfo.positive_oos_windows),
        "oos_window_count": float(len(wfo.oos_metrics)),
        "ruin_rate_pct": float(robustness.summary.ruin_rate_pct),
        "median_ending_equity": float(robustness.summary.median_ending_equity),
        "worst_ending_equity": float(robustness.summary.worst_ending_equity),
        "median_max_drawdown": float(robustness.summary.median_max_drawdown),
        "worst_max_drawdown": float(robustness.summary.worst_max_drawdown),
        "simulations": float(robustness.summary.simulations),
    }
    if any(not isfinite(value) for value in values.values()):
        raise ValueError("validation metrics must be finite")
    return values


def _run_once(
    data: Sequence[Any],
    parameter_sets: Sequence[Mapping[str, Any]],
    evaluator: BacktestEvaluator,
    *,
    train_size: int,
    test_size: int,
    purge_size: int,
    step: int | None,
    maximize: bool,
    objective: MetricEvaluator,
    context_size: int,
    context_evaluator: ContextBacktestEvaluator | None,
    starting_equity: float,
    simulations: int,
    seed: int | None,
    slippage_multiplier: float,
    spread_multiplier: float,
    policy: EvidenceGatePolicy,
    provenance: ResearchProvenance,
    dataset_id: str,
    version: str,
    data_manifest: Mapping[str, object],
    config_manifest: Mapping[str, object],
) -> ResearchValidationResult:
    wfo = run_backtest_wfo(
        data,
        parameter_sets,
        evaluator,
        train_size=train_size,
        test_size=test_size,
        purge_size=purge_size,
        step=step,
        maximize=maximize,
        objective=objective,
        context_size=context_size,
        context_evaluator=context_evaluator,
    )
    robustness = run_oos_monte_carlo(
        wfo,
        starting_equity=starting_equity,
        simulations=simulations,
        seed=seed,
        slippage_multiplier=slippage_multiplier,
        spread_multiplier=spread_multiplier,
    )
    release = evaluate_research_release(wfo, robustness, policy)
    evidence = ResearchEvidence.create(
        dataset_id,
        version,
        samples=len(data),
        metrics=_metric_payload(wfo, robustness),
        data=data_manifest,
        config=config_manifest,
        code_revision=provenance.code_revision,
    )
    # The evidence constructor fingerprints the supplied manifests. Requiring
    # those fingerprints to equal the pre-built provenance prevents accidental
    # provenance drift inside the harness.
    if evidence.provenance != provenance:
        raise ValueError("evidence provenance drift detected")
    result = ResearchValidationResult(provenance, wfo, robustness, release, evidence)
    result.validate()
    return result


def run_research_validation(
    data: Sequence[Any],
    parameter_sets: Sequence[Mapping[str, Any]],
    evaluator: BacktestEvaluator,
    *,
    data_manifest: Mapping[str, object],
    config_manifest: Mapping[str, object],
    code_revision: str,
    data_fingerprint_fn: Callable[[Sequence[Any]], str] | None = None,
    dataset_id: str,
    version: str,
    train_size: int,
    test_size: int,
    purge_size: int,
    starting_equity: float,
    simulations: int = 1000,
    seed: int | None = 42,
    step: int | None = None,
    maximize: bool = True,
    objective: MetricEvaluator = lambda metrics: metrics.expectancy,
    context_size: int = 0,
    context_evaluator: ContextBacktestEvaluator | None = None,
    slippage_multiplier: float = 1.0,
    spread_multiplier: float = 1.0,
    policy: EvidenceGatePolicy = EvidenceGatePolicy(),
) -> ResearchValidationResult:
    """Run one complete, provenance-bound, fail-closed research validation."""
    if not callable(data_fingerprint_fn):
        raise ValueError("data_fingerprint_fn is required and must be callable")
    actual_fingerprint = data_fingerprint_fn(data)
    if not isinstance(actual_fingerprint, str) or not actual_fingerprint.strip():
        raise ValueError("data_fingerprint_fn must return a non-empty string")
    effective_data_manifest = dict(data_manifest)
    effective_data_manifest["sequence_fingerprint"] = actual_fingerprint

    # Bind every deterministic execution control to provenance. A caller cannot
    # silently reuse the same dataset/config identity while changing WFO or MC
    # controls and still obtain the same research identity.
    effective_config_manifest = dict(config_manifest)
    effective_config_manifest["validation_controls"] = {
        "train_size": train_size,
        "test_size": test_size,
        "purge_size": purge_size,
        "step": step,
        "maximize": maximize,
        "context_size": context_size,
        "starting_equity": starting_equity,
        "simulations": simulations,
        "seed": seed,
        "slippage_multiplier": slippage_multiplier,
        "spread_multiplier": spread_multiplier,
        "parameter_sets": [dict(params) for params in parameter_sets],
        "policy": {
            "min_oos_trades": policy.min_oos_trades,
            "min_expectancy": policy.min_expectancy,
            "min_oos_stability_pct": policy.min_oos_stability_pct,
            "max_ruin_rate_pct": policy.max_ruin_rate_pct,
            "max_worst_drawdown": policy.max_worst_drawdown,
        },
    }
    provenance = build_provenance(
        data=effective_data_manifest,
        config=effective_config_manifest,
        code_revision=code_revision,
    )
    return _run_once(
        data,
        parameter_sets,
        evaluator,
        train_size=train_size,
        test_size=test_size,
        purge_size=purge_size,
        step=step,
        maximize=maximize,
        objective=objective,
        context_size=context_size,
        context_evaluator=context_evaluator,
        starting_equity=starting_equity,
        simulations=simulations,
        seed=seed,
        slippage_multiplier=slippage_multiplier,
        spread_multiplier=spread_multiplier,
        policy=policy,
        provenance=provenance,
        dataset_id=dataset_id,
        version=version,
        data_manifest=effective_data_manifest,
        config_manifest=effective_config_manifest,
    )


def assert_reproducible(first: ResearchValidationResult, second: ResearchValidationResult) -> None:
    """Fail closed unless provenance and canonical evidence are identical."""
    if not isinstance(first, ResearchValidationResult) or not isinstance(second, ResearchValidationResult):
        raise ValueError("validation results must be ResearchValidationResult")
    first.validate()
    second.validate()
    if first.provenance != second.provenance:
        raise ValueError("research validation provenance is not reproducible")
    if first.evidence.evidence_hash != second.evidence.evidence_hash:
        raise ValueError("research validation evidence is not reproducible")
