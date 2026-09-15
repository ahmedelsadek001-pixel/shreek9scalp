"""Backtest-aware purged walk-forward validation for SHREEK V5.2."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Callable, Mapping, Sequence

from core.backtest_engine import BacktestResult
from core.research_metrics import ResearchMetrics, calculate_research_metrics
from research.purged_wfo import PurgedWFOResult, build_purged_windows


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
    def oos_trade_pnl(self) -> tuple[float, ...]:
        """Flatten realized net P&L from actual OOS trades in window order."""
        pnl = tuple(trade.net_pnl for result in self.oos_results for trade in result.trades)
        if any(not isfinite(float(value)) for value in pnl):
            raise ValueError("OOS trade P&L must be finite")
        return pnl

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
    """Select parameters on train backtests and evaluate each OOS slice once.

    The evaluator must run a causal backtest over the supplied slice. Parameters
    are selected using only train metrics; the selected parameters are then run
    once on each embargoed OOS slice. No OOS metric participates in selection,
    and the same OOS result is retained as the source for all reported metrics.
    """
    if not callable(evaluator):
        raise ValueError("evaluator must be callable")
    if type(maximize) is not bool:
        raise ValueError("maximize must be a bool")
    if not parameter_sets:
        raise ValueError("parameter_sets must be non-empty")

    windows = build_purged_windows(
        len(data), train_size, test_size, purge_size, step
    )
    train_scores: list[float] = []
    test_scores: list[float] = []
    selected_parameters: list[Mapping[str, Any]] = []
    train_metrics: list[ResearchMetrics] = []
    oos_metrics: list[ResearchMetrics] = []
    oos_results: list[BacktestResult] = []

    for window in windows:
        train = data[window.train_start : window.train_end]
        test = data[window.test_start : window.test_end]
        scored: list[tuple[float, Mapping[str, Any], BacktestResult, ResearchMetrics]] = []
        for params in parameter_sets:
            train_result = evaluator(train, params)
            if not isinstance(train_result, BacktestResult):
                raise ValueError("evaluator must return a BacktestResult")
            metrics = calculate_research_metrics(train_result)
            scored.append((_score_metric(metrics, objective), params, train_result, metrics))

        scored.sort(key=lambda item: item[0], reverse=maximize)
        train_score, params, train_result, selected_train_metrics = scored[0]
        oos_result = evaluator(test, params)
        if not isinstance(oos_result, BacktestResult):
            raise ValueError("evaluator must return a BacktestResult")
        oos_metric = calculate_research_metrics(oos_result)
        test_score = _score_metric(oos_metric, objective)

        train_scores.append(train_score)
        test_scores.append(test_score)
        selected_parameters.append(dict(params))
        train_metrics.append(selected_train_metrics)
        oos_metrics.append(oos_metric)
        oos_results.append(oos_result)

    validation = PurgedWFOResult(
        tuple(windows),
        tuple(train_scores),
        tuple(test_scores),
        tuple(selected_parameters),
    )
    return BacktestWFOResult(
        validation,
        tuple(train_metrics),
        tuple(oos_metrics),
        tuple(oos_results),
    )
