"""Purged/embargoed walk-forward validation primitives for SHREEK V5.2."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Callable, Mapping, Sequence


@dataclass(frozen=True)
class PurgedWindow:
    train_start: int
    train_end: int
    purge_start: int
    purge_end: int
    test_start: int
    test_end: int


@dataclass(frozen=True)
class PurgedWFOResult:
    windows: tuple[PurgedWindow, ...]
    train_scores: tuple[float, ...]
    test_scores: tuple[float, ...]
    selected_parameters: tuple[Mapping[str, Any], ...]


def build_purged_windows(
    length: int,
    train_size: int,
    test_size: int,
    purge_size: int,
    step: int | None = None,
) -> tuple[PurgedWindow, ...]:
    """Build chronological windows with an explicit purge/embargo gap.

    ``purge_size`` is caller-supplied and must cover the strategy's maximum
    information/label-overlap horizon. This primitive enforces the gap, but
    cannot infer that horizon from an arbitrary evaluator.
    """
    if any(type(value) is not int for value in (length, train_size, test_size, purge_size)):
        raise ValueError("length, train_size, test_size and purge_size must be integers")
    if length <= 0 or train_size <= 0 or test_size <= 0:
        raise ValueError("length, train_size and test_size must be positive")
    if purge_size < 0:
        raise ValueError("purge_size must be non-negative")
    if step is None:
        step = test_size
    elif type(step) is not int:
        raise ValueError("step must be an integer")
    if step <= 0:
        raise ValueError("step must be positive")
    if step < test_size:
        raise ValueError("step must be at least test_size to prevent overlapping OOS windows")

    windows = []
    start = 0
    while start + train_size + purge_size + test_size <= length:
        train_end = start + train_size
        purge_end = train_end + purge_size
        test_end = purge_end + test_size
        windows.append(PurgedWindow(start, train_end, train_end, purge_end, purge_end, test_end))
        start += step
    if not windows:
        raise ValueError("insufficient data for one purged walk-forward window")
    return tuple(windows)


def _validated_score(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("evaluator scores must be numeric and not boolean")
    score = float(value)
    if not isfinite(score):
        raise ValueError("evaluator scores must be finite")
    return score


def run_purged_wfo(
    data: Sequence[Any],
    parameter_sets: Sequence[Mapping[str, Any]],
    evaluator: Callable[[Sequence[Any], Mapping[str, Any]], float],
    *,
    train_size: int,
    test_size: int,
    purge_size: int,
    step: int | None = None,
    maximize: bool = True,
) -> PurgedWFOResult:
    """Select parameters on train data only and evaluate after an embargo gap."""
    if not parameter_sets:
        raise ValueError("parameter_sets must be non-empty")
    if not callable(evaluator):
        raise ValueError("evaluator must be callable")
    if type(maximize) is not bool:
        raise ValueError("maximize must be a boolean")
    if any(not isinstance(params, Mapping) for params in parameter_sets):
        raise ValueError("each parameter set must be a mapping")

    windows = build_purged_windows(len(data), train_size, test_size, purge_size, step)
    train_scores: list[float] = []
    test_scores: list[float] = []
    selected: list[Mapping[str, Any]] = []
    for window in windows:
        train = data[window.train_start : window.train_end]
        test = data[window.test_start : window.test_end]
        scored = []
        for params in parameter_sets:
            score = _validated_score(evaluator(train, params))
            scored.append((score, params))
        scored.sort(key=lambda item: item[0], reverse=maximize)
        train_score, params = scored[0]
        test_score = _validated_score(evaluator(test, params))
        train_scores.append(train_score)
        test_scores.append(test_score)
        selected.append(dict(params))
    return PurgedWFOResult(tuple(windows), tuple(train_scores), tuple(test_scores), tuple(selected))
