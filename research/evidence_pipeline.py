"""End-to-end research evidence assembly for SHREEK V5.2.

This module composes causal backtest WFO, OOS Monte Carlo, the immutable
OOS evidence report, and the research-only evidence gate. It never grants
execution or deployment authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping, Sequence

from core.block_bootstrap import BlockBootstrapSummary, moving_block_bootstrap
from core.research_certification import (
    ResearchCertification,
    ResearchCertificationPolicy,
    certify_research,
)
from core.statistical_evidence import MeanConfidenceInterval, mean_confidence_interval
from research.backtest_wfo import (
    BacktestEvaluator,
    BacktestWFOResult,
    ContextBacktestEvaluator,
    MetricEvaluator,
    run_backtest_wfo,
)
from research.evidence_gate import EvidenceGatePolicy, EvidenceGateResult, evaluate_oos_evidence
from research.evidence_report import OOSEvidenceReport, build_oos_evidence_report
from research.robustness import RobustnessEvidence, run_oos_monte_carlo


def _expectancy_objective(metrics: Any) -> float:
    return metrics.expectancy


@dataclass(frozen=True)
class ResearchRunConfig:
    """Exact research controls required to reproduce one evidence run."""

    train_size: int
    test_size: int
    purge_size: int
    step: int
    maximize: bool
    starting_equity: float
    simulations: int
    seed: int | None
    slippage_multiplier: float
    spread_multiplier: float
    confidence: float
    bootstrap_block_size: int
    bootstrap_simulations: int
    label_horizon: int
    objective_id: str
    candidate_parameters: tuple[Mapping[str, Any], ...]
    context_size: int = 0
    context_evaluator_id: str | None = None

    def validate(self) -> None:
        if any(type(value) is not int or value <= 0 for value in (
            self.train_size, self.test_size, self.step, self.simulations,
            self.bootstrap_block_size, self.bootstrap_simulations,
        )):
            raise ValueError("research run positive integer controls are invalid")
        if type(self.purge_size) is not int or self.purge_size < 0:
            raise ValueError("research run purge_size is invalid")
        if type(self.label_horizon) is not int or self.label_horizon < 0:
            raise ValueError("research run label_horizon is invalid")
        if self.purge_size < self.label_horizon:
            raise ValueError("research run purge_size must cover label_horizon")
        if self.step < self.test_size:
            raise ValueError("research run step must prevent overlapping OOS windows")
        if type(self.maximize) is not bool:
            raise ValueError("research run maximize must be a bool")
        if (
            type(self.starting_equity) not in (int, float)
            or not isfinite(float(self.starting_equity))
            or self.starting_equity <= 0
        ):
            raise ValueError("research run starting_equity must be positive and finite")
        if self.seed is not None and type(self.seed) is not int:
            raise ValueError("research run seed must be an integer or None")
        if any(
            type(value) not in (int, float) or not isfinite(float(value)) or value < 1
            for value in (self.slippage_multiplier, self.spread_multiplier)
        ):
            raise ValueError("research run cost multipliers must be numeric and >= 1")
        if (
            type(self.confidence) not in (int, float)
            or not isfinite(float(self.confidence))
            or not 0 < self.confidence < 1
        ):
            raise ValueError("research run confidence must be between zero and one")
        if not isinstance(self.objective_id, str) or not self.objective_id.strip():
            raise ValueError("research run objective_id must be non-empty")
        if not self.candidate_parameters or any(
            not isinstance(params, Mapping) for params in self.candidate_parameters
        ):
            raise ValueError("research run candidate parameters must be non-empty mappings")
        if type(self.context_size) is not int or self.context_size < 0:
            raise ValueError("research run context_size must be a non-negative integer")
        if self.context_size > 0:
            if not isinstance(self.context_evaluator_id, str) or not self.context_evaluator_id.strip():
                raise ValueError("research run warm-up context requires a context evaluator identity")
        elif self.context_evaluator_id is not None:
            raise ValueError("research run context evaluator identity requires warm-up context")


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
    run_config: ResearchRunConfig | None = None


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
    objective: MetricEvaluator = _expectancy_objective,
    objective_id: str | None = None,
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
) -> EvidencePipelineResult:
    """Run the complete V5.2 evidence chain in causal order.

    Parameter selection occurs only on train data. Monte Carlo consumes only
    realized OOS trades. The final gate evaluates the documented evidence and
    remains strictly research-only.
    """
    if objective_id is None:
        if objective is not _expectancy_objective:
            raise ValueError("custom research objective requires explicit objective_id")
        resolved_objective_id = "expectancy"
    elif not isinstance(objective_id, str) or not objective_id.strip():
        raise ValueError("objective_id must be non-empty")
    elif objective is _expectancy_objective and objective_id != "expectancy":
        raise ValueError("default expectancy objective must use objective_id='expectancy'")
    else:
        resolved_objective_id = objective_id.strip()
    if type(context_size) is not int or context_size < 0:
        raise ValueError("context_size must be a non-negative integer")
    if context_size > 0:
        if not callable(context_evaluator):
            raise ValueError("context_evaluator is required when context_size is positive")
        if not isinstance(context_evaluator_id, str) or not context_evaluator_id.strip():
            raise ValueError("context_evaluator_id is required for warm-up context")
        resolved_context_evaluator_id = context_evaluator_id.strip()
    else:
        if context_evaluator is not None or context_evaluator_id is not None:
            raise ValueError("context evaluator requires a positive context_size")
        resolved_context_evaluator_id = None
    resolved_step = test_size if step is None else step
    run_config = ResearchRunConfig(
        train_size,
        test_size,
        purge_size,
        resolved_step,
        maximize,
        starting_equity,
        simulations,
        seed,
        slippage_multiplier,
        spread_multiplier,
        confidence,
        bootstrap_block_size,
        bootstrap_simulations,
        label_horizon,
        resolved_objective_id,
        tuple(dict(params) for params in parameter_sets),
        context_size,
        resolved_context_evaluator_id,
    )
    run_config.validate()
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
        label_horizon=label_horizon,
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
        run_config,
    )
