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
ContextBacktestEvaluator = Callable[[Sequence[Any], Mapping[str, Any], int], BacktestResult]


@dataclass(frozen=True)
class BacktestWFOResult:
    """Purged WFO selection plus the actual train/OOS backtest evidence."""

    validation: PurgedWFOResult
    train_metrics: tuple[ResearchMetrics, ...]
    oos_metrics: tuple[ResearchMetrics, ...]
    oos_results: tuple[BacktestResult, ...]

    @property
    def oos_expectancy(self) -> float:
        trades = sum(metric.trades for metric in self.oos_metrics)
        if trades == 0:
            return 0.0
        return sum(metric.expectancy * metric.trades for metric in self.oos_metrics) / trades

    @property
    def oos_net_pnl(self) -> float:
        return sum(metric.net_pnl for metric in self.oos_metrics)

    @property
    def oos_trade_pnl(self) -> tuple[float, ...]:
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


def _validate_context_result(
    result: BacktestResult,
    contextual_data: Sequence[Any],
    oos_start_index: int,
    oos_end_index: int,
) -> None:
    """Reject trades that cross either side of the exact OOS interval."""
    if type(oos_start_index) is not int or type(oos_end_index) is not int:
        raise ValueError("OOS boundaries must be integers")
    if not contextual_data or not 0 <= oos_start_index < oos_end_index <= len(contextual_data):
        raise ValueError("invalid contextual OOS boundaries")
    if not all(hasattr(item, "timestamp") for item in contextual_data):
        raise ValueError("contextual OOS data must expose timestamp")
    try:
        timestamps = [item.timestamp for item in contextual_data]
        if any(a >= b for a, b in zip(timestamps, timestamps[1:])):
            raise ValueError("contextual OOS timestamps must be chronological")
        oos_start = timestamps[oos_start_index]
        oos_end = timestamps[oos_end_index - 1]
        for trade in result.trades:
            signal_time = getattr(trade, "signal_time", None)
            entry_time = getattr(trade, "entry_time", None)
            exit_time = getattr(trade, "exit_time", None)
            if signal_time is None or entry_time is None or exit_time is None:
                raise ValueError("OOS trades must expose signal_time, entry_time and exit_time")
            if signal_time < oos_start or entry_time < oos_start or exit_time > oos_end:
                raise ValueError("OOS backtest produced a trade outside the OOS interval")
            if entry_time < signal_time or exit_time < entry_time:
                raise ValueError("OOS backtest produced non-chronological trade timestamps")
    except TypeError as exc:
        raise ValueError("OOS timestamps must be mutually comparable") from exc


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
    context_size: int = 0,
    context_evaluator: ContextBacktestEvaluator | None = None,
) -> BacktestWFOResult:
    """Select on train and evaluate each exact OOS interval once, fail-closed."""
    if not callable(evaluator):
        raise ValueError("evaluator must be callable")
    if type(maximize) is not bool:
        raise ValueError("maximize must be a bool")
    if type(context_size) is not int or context_size < 0:
        raise ValueError("context_size must be a non-negative integer")
    if context_size > 0 and not callable(context_evaluator):
        raise ValueError("context_evaluator is required when context_size is positive")
    if not parameter_sets:
        raise ValueError("parameter_sets must be non-empty")

    windows = build_purged_windows(len(data), train_size, test_size, purge_size, step)
    train_scores: list[float] = []
    test_scores: list[float] = []
    selected_parameters: list[Mapping[str, Any]] = []
    train_metrics: list[ResearchMetrics] = []
    oos_metrics: list[ResearchMetrics] = []
    oos_results: list[BacktestResult] = []

    for window in windows:
        train = data[window.train_start : window.train_end]
        scored: list[tuple[float, Mapping[str, Any], ResearchMetrics]] = []
        for params in parameter_sets:
            train_result = evaluator(train, params)
            if not isinstance(train_result, BacktestResult):
                raise ValueError("evaluator must return a BacktestResult")
            metrics = calculate_research_metrics(train_result)
            scored.append((_score_metric(metrics, objective), params, metrics))
        scored.sort(key=lambda item: item[0], reverse=maximize)
        train_score, params, selected_train_metrics = scored[0]

        if context_size:
            context_start = max(0, window.test_start - context_size)
            oos_slice = data[context_start : window.test_end]
            oos_start_index = window.test_start - context_start
            oos_end_index = window.test_end - context_start
            oos_result = context_evaluator(oos_slice, params, oos_start_index)  # type: ignore[misc]
            _validate_context_result(oos_result, oos_slice, oos_start_index, oos_end_index)
        else:
            oos_slice = data[window.test_start : window.test_end]
            oos_result = evaluator(oos_slice, params)
        if not isinstance(oos_result, BacktestResult):
            raise ValueError("OOS evaluator must return a BacktestResult")
        oos_metric = calculate_research_metrics(oos_result)
        test_score = _score_metric(oos_metric, objective)

        train_scores.append(train_score)
        test_scores.append(test_score)
        selected_parameters.append(dict(params))
        train_metrics.append(selected_train_metrics)
        oos_metrics.append(oos_metric)
        oos_results.append(oos_result)

    validation = PurgedWFOResult(tuple(windows), tuple(train_scores), tuple(test_scores), tuple(selected_parameters))
    return BacktestWFOResult(validation, tuple(train_metrics), tuple(oos_metrics), tuple(oos_results))
