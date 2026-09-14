"""Backtest-aware purged walk-forward validation for SHREEK V5.2."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Callable, Mapping, Sequence

from core.backtest_engine import BacktestResult
from core.research_metrics import ResearchMetrics, calculate_research_metrics
from research.purged_wfo import PurgedWFOResult, run_purged_wfo


MetricEvaluator = Callable[[ResearchMetrics], float]
BacktestEvaluator = Callable[[Sequence[Any], Mapping[str, Any]], BacktestResult]


@dataclass(frozen=True)
class BacktestWFOResult:
    """Purged WFO selection plus the actual train/OOS backtest evidence."""

    validation: PurgedWFOResult
    train_metrics: tuple[ResearchMetrics, ...]
    oos_metrics: tuple[ResearchMetrics, ...]
    oos_results: tuple[BacktestResult, ...]

    @property
    def oos_expectancy(self) -> float:
        """Trade-weighted expectancy across all OOS trades."""
        trades = sum(metric.trades for metric in self.oos_metrics)
        if trades == 0:
            return 0.0
        return sum(metric.expectancy * metric.trades for metric in self.oos_metrics) / trades

    @property
    def oos_net_pnl(self) -> float:
        """Total realized net P&L across OOS windows."""
        return sum(metric.net_pnl for metric in self.oos_metrics)

    @property
    def positive_oos_windows(self) -> int:
        return sum(metric.net_pnl > 0 for metric in self.oos_metrics)

    @property
    def oos_stability_pct(self) -> float:
        return self.positive_oos_windows / len(self.oos_metrics) * 100.0 if self.oos_metrics else 0.0


def _score_metric(metrics: ResearchMetrics, objective: MetricEvaluator) -> float:
    if not callable(objective):
        raise ValueError("objective must be callable")
    score = float(objective(metrics))
    if not isfinite(score):
        raise ValueError("objective scores must be finite")
    return score


def run_backtest_wfo(
    data: Sequence[Any],
    parameter_sets: Sequence[Mapping[str, Any]],
    evaluator: BacktestEvaluator,
    *,
    train_size: int,
    test_size: int,
    purge_size: int,
    step: int | None = None,
    maximize: bool = True,
    objective: MetricEvaluator = lambda metrics: metrics.expectancy,
) -> BacktestWFOResult:
    """Select parameters from realized train backtests and collect OOS evidence.

    The evaluator must run a causal backtest over the supplied slice. Parameters
    are selected using only train metrics; the selected parameters are then run
    once on each embargoed OOS slice. No OOS metric participates in selection.
    """
    if not callable(evaluator):
        raise ValueError("evaluator must be callable")
    if type(maximize) is not bool:
        raise ValueError("maximize must be a bool")
    if not parameter_sets:
        raise ValueError("parameter_sets must be non-empty")

    def score(rows: Sequence[Any], params: Mapping[str, Any]) -> float:
        result = evaluator(rows, params)
        if not isinstance(result, BacktestResult):
            raise ValueError("evaluator must return a BacktestResult")
        return _score_metric(calculate_research_metrics(result), objective)

    validation = run_purged_wfo(
        data,
        parameter_sets,
        score,
        train_size=train_size,
        test_size=test_size,
        purge_size=purge_size,
        step=step,
        maximize=maximize,
    )

    train_metrics: list[ResearchMetrics] = []
    oos_metrics: list[ResearchMetrics] = []
    oos_results: list[BacktestResult] = []
    for window, params in zip(validation.windows, validation.selected_parameters):
        train_result = evaluator(data[window.train_start : window.train_end], params)
        oos_result = evaluator(data[window.test_start : window.test_end], params)
        if not isinstance(train_result, BacktestResult) or not isinstance(oos_result, BacktestResult):
            raise ValueError("evaluator must return a BacktestResult")
        train_metrics.append(calculate_research_metrics(train_result))
        oos_metrics.append(calculate_research_metrics(oos_result))
        oos_results.append(oos_result)

    return BacktestWFOResult(
        validation,
        tuple(train_metrics),
        tuple(oos_metrics),
        tuple(oos_results),
    )
