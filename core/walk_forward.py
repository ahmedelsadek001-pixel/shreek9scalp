"""Causal walk-forward validation primitives for SHREEK V5.1."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Callable, Mapping, Optional, Sequence


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


def rolling_windows(
    length: int,
    train_size: int,
    test_size: int,
    step: Optional[int] = None,
    purge_size: int = 0,
) -> tuple[WalkForwardWindow, ...]:
    """Create chronological train/test windows with an optional embargo gap.

    ``purge_size`` removes observations immediately after the training set
    from test evaluation, reducing leakage from labels or features whose
    information horizon crosses the train/test boundary.
    """
    if length <= 0 or train_size <= 0 or test_size <= 0:
        raise ValueError("window sizes and length must be positive")
    if purge_size < 0:
        raise ValueError("purge_size must be non-negative")
    step = test_size if step is None else step
    if step <= 0:
        raise ValueError("step must be positive")
    windows = []
    start = 0
    while start + train_size + purge_size + test_size <= length:
        train_end = start + train_size
        test_start = train_end + purge_size
        windows.append(
            WalkForwardWindow(start, train_end, test_start, test_start + test_size)
        )
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
    step: Optional[int] = None,
    maximize: bool = True,
    purge_size: int = 0,
) -> WalkForwardSummary:
    """Select parameters only on training data, then evaluate them OOS."""
    if not parameter_sets:
        raise ValueError("parameter_sets must be non-empty")
    if not callable(evaluator):
        raise ValueError("evaluator must be callable")
    if type(maximize) is not bool:
        raise ValueError("maximize must be a bool")
    windows = rolling_windows(len(data), train_size, test_size, step, purge_size)
    results = []
    for window in windows:
        train = data[window.train_start : window.train_end]
        test = data[window.test_start : window.test_end]
        scored = [(_score(evaluator(train, params)), params) for params in parameter_sets]
        scored.sort(key=lambda item: item[0], reverse=maximize)
        train_score, selected = scored[0]
        test_score = _score(evaluator(test, selected))
        results.append(WalkForwardResult(window, dict(selected), train_score, test_score))
    test_scores = sorted(result.test_score for result in results)
    count = len(test_scores)
    if count % 2:
        median = test_scores[count // 2]
    else:
        median = (test_scores[count // 2 - 1] + test_scores[count // 2]) / 2.0
    aggregate = sum(test_scores) / count
    positive = sum(score > 0 for score in test_scores)
    return WalkForwardSummary(
        tuple(results), aggregate, median, positive, positive / count * 100.0
    )
