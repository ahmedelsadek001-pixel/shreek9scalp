"""Walk-forward validation primitives for SHREEK V5.1.

The engine is optimizer-agnostic: callers provide a deterministic evaluator that
maps (bars, parameters) to a score. Training data is used only to select a
parameter set; the selected set is then evaluated on the following validation
window. No broker I/O or order authority exists here.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite
from typing import Any, Callable, Mapping, Sequence

@dataclass(frozen=True)
class WalkForwardWindow:
    train_start: int
    train_end: int
    test_start: int
    test_end: int

@dataclass(frozen=True)
class WalkForwardResult:
    window: WalkForwardWindow
    parameters: Mapping[str, Any]
    train_score: float
    test_score: float

@dataclass(frozen=True)
class WalkForwardSummary:
    windows: tuple[WalkForwardResult, ...]
    aggregate_test_score: float
    median_test_score: float
    positive_test_windows: int
    stability_pct: float


def _score(value: Any) -> float:
    result = float(value)
    if not isfinite(result):
        raise ValueError("evaluator scores must be finite")
    return result


def rolling_windows(length: int, train_size: int, test_size: int, step: int | None = None) -> tuple[WalkForwardWindow, ...]:
    """Create non-overlapping test windows with expanding/rolling training slices."""
    if length <= 0 or train_size <= 0 or test_size <= 0:
        raise ValueError("window sizes and length must be positive")
    step = test_size if step is None else step
    if step <= 0:
        raise ValueError("step must be positive")
    windows = []
    start = 0
    while start + train_size + test_size <= length:
        windows.append(WalkForwardWindow(start, start + train_size, start + train_size, start + train_size + test_size))
        start += step
    if not windows:
        raise ValueError("insufficient data for one walk-forward window")
    return tuple(windows)


def run_walk_forward(
    data: Sequence[Any],
    parameter_sets: Sequence[Mapping[str, Any]],
    evaluator: Callable[[Sequence[Any], Mapping[str, Any]], float],
    train_size: int,
    test_size: int,
    step: int | None = None,
    maximize: bool = True,
) -> WalkForwardSummary:
    """Select parameters on each training slice and score them out-of-sample."""
    if not parameter_sets:
        raise ValueError("parameter_sets must be non-empty")
    if not callable(evaluator):
        raise ValueError("evaluator must be callable")
    windows = rolling_windows(len(data), train_size, test_size, step)
    results = []
    for window in windows:
        train = data[window.train_start:window.train_end]
        test = data[window.test_start:window.test_end]
        scored = [(_score(evaluator(train, params)), params) for params in parameter_sets]
        scored.sort(key=lambda item: item[0], reverse=maximize)
        train_score, selected = scored[0]
        test_score = _score(evaluator(test, selected))
        results.append(WalkForwardResult(window, dict(selected), train_score, test_score))
    test_scores = sorted(result.test_score for result in results)
    median = test_scores[len(test_scores) // 2] if len(test_scores) % 2 else (test_scores[len(test_scores)//2-1] + test_scores[len(test_scores)//2]) / 2
    aggregate = sum(test_scores) / len(test_scores)
    positive = sum(score > 0 for score in test_scores)
    return WalkForwardSummary(tuple(results), aggregate, median, positive, positive / len(test_scores) * 100.0)
