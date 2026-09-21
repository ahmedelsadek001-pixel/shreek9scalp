"""End-to-end research evidence assembly for SHREEK V5.2.

This module composes causal backtest WFO, OOS Monte Carlo, the immutable
OOS evidence report, and the research-only evidence gate. It never grants
execution or deployment authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from core.block_bootstrap import BlockBootstrapSummary, moving_block_bootstrap
from core.research_certification import (
    ResearchCertification,
    ResearchCertificationPolicy,
    certify_research,
)
from core.statistical_evidence import MeanConfidenceInterval, mean_confidence_interval
from research.backtest_wfo import BacktestEvaluator, BacktestWFOResult, MetricEvaluator, run_backtest_wfo
from research.evidence_gate import EvidenceGatePolicy, EvidenceGateResult, evaluate_oos_evidence
from research.evidence_report import OOSEvidenceReport, build_oos_evidence_report
from research.robustness import RobustnessEvidence, run_oos_monte_carlo


@dataclass(frozen=True)
class EvidencePipelineResult:
    """Complete research evidence bundle plus its fail-closed gate decision."""

    wfo: BacktestWFOResult
    robustness: RobustnessEvidence
    report: OOSEvidenceReport
    gate: EvidenceGateResult
    policy: EvidenceGatePolicy = EvidenceGatePolicy()
    interval: MeanConfidenceInterval | None = None
    bootstrap: BlockBootstrapSummary | None = None
    certification: ResearchCertification | None = None
    certification_policy: ResearchCertificationPolicy = ResearchCertificationPolicy()


def run_evidence_pipeline(
    data: Sequence[Any],
    parameter_sets: Sequence[Mapping[str, Any]],
    evaluator: BacktestEvaluator,
    *,
    train_size: int,
    test_size: int,
    purge_size: int,
    starting_equity: float,
    step: int | None = None,
    maximize: bool = True,
    objective: MetricEvaluator = lambda metrics: metrics.expectancy,
    simulations: int = 1000,
    seed: int | None = 42,
    slippage_multiplier: float = 1.0,
    spread_multiplier: float = 1.0,
    policy: EvidenceGatePolicy = EvidenceGatePolicy(),
    confidence: float = 0.95,
    bootstrap_block_size: int = 2,
    bootstrap_simulations: int = 2000,
    certification_policy: ResearchCertificationPolicy = ResearchCertificationPolicy(),
) -> EvidencePipelineResult:
    """Run the complete V5.2 evidence chain in causal order.

    Parameter selection occurs only on train data. Monte Carlo consumes only
    realized OOS trades. The final gate evaluates the documented evidence and
    remains strictly research-only.
    """
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
    )
    robustness = run_oos_monte_carlo(
        wfo,
        starting_equity=starting_equity,
        simulations=simulations,
        seed=seed,
        slippage_multiplier=slippage_multiplier,
        spread_multiplier=spread_multiplier,
    )
    report = build_oos_evidence_report(wfo, robustness)
    gate = evaluate_oos_evidence(report, policy)
    pnl = wfo.oos_trade_pnl
    interval = mean_confidence_interval(pnl, confidence)
    bootstrap = moving_block_bootstrap(
        pnl,
        block_size=bootstrap_block_size,
        simulations=bootstrap_simulations,
        confidence=confidence,
        seed=42 if seed is None else seed,
    )
    certification = certify_research(
        wfo,
        interval,
        bootstrap,
        robustness,
        certification_policy,
    )
    return EvidencePipelineResult(
        wfo,
        robustness,
        report,
        gate,
        policy,
        interval,
        bootstrap,
        certification,
        certification_policy,
    )
