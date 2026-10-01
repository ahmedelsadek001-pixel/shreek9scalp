"""Deterministic block-bootstrap diagnostics for dependent trade PnL."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from random import Random
from statistics import median
from typing import Iterable


@dataclass(frozen=True)
class BlockBootstrapSummary:
    samples: int
    block_size: int
    simulations: int
    confidence: float
    observed_mean: float
    median_mean: float
    lower_mean: float
    upper_mean: float
    non_positive_mean_rate_pct: float

    def validate(self) -> None:
        if type(self.samples) is not int or self.samples < 2:
            raise ValueError("bootstrap requires at least two samples")
        if type(self.block_size) is not int or not 1 <= self.block_size <= self.samples:
            raise ValueError("invalid block size")
        if type(self.simulations) is not int or self.simulations < 2:
            raise ValueError("bootstrap requires at least two simulations")
        values = (self.confidence, self.observed_mean, self.median_mean, self.lower_mean,
                  self.upper_mean, self.non_positive_mean_rate_pct)
        if not all(isfinite(float(v)) for v in values):
            raise ValueError("bootstrap summary values must be finite")
        if not 0.0 < self.confidence < 1.0 or not 0.0 <= self.non_positive_mean_rate_pct <= 100.0:
            raise ValueError("invalid bootstrap probability")
        if self.lower_mean > self.median_mean or self.median_mean > self.upper_mean:
            raise ValueError("invalid bootstrap quantiles")


def _sample(values: Iterable[float]) -> tuple[float, ...]:
    try:
        raw = tuple(values)
    except TypeError as exc:
        raise ValueError("pnl must be iterable") from exc
    if len(raw) < 2:
        raise ValueError("bootstrap requires at least two pnl observations")
    result = []
    for value in raw:
        if isinstance(value, bool):
            raise ValueError("pnl observations must be finite numbers")
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("pnl observations must be finite numbers") from exc
        if not isfinite(number):
            raise ValueError("pnl observations must be finite numbers")
        result.append(number)
    return tuple(result)


def _quantile(sorted_values: tuple[float, ...], probability: float) -> float:
    position = probability * (len(sorted_values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def moving_block_bootstrap(
    pnl: Iterable[float], *, block_size: int, simulations: int = 2000,
    confidence: float = 0.95, seed: int = 42,
) -> BlockBootstrapSummary:
    """Resample contiguous circular PnL blocks to retain short-range dependence."""
    values = _sample(pnl)
    n = len(values)
    if type(block_size) is not int or not 1 <= block_size <= n:
        raise ValueError("block_size must be an integer between one and sample size")
    if type(simulations) is not int or simulations < 2:
        raise ValueError("simulations must be an integer of at least two")
    if isinstance(confidence, bool):
        raise ValueError("confidence must be numeric")
    try:
        level = float(confidence)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("confidence must be numeric") from exc
    if not isfinite(level) or not 0.0 < level < 1.0:
        raise ValueError("confidence must be between zero and one")
    if type(seed) is not int:
        raise ValueError("seed must be an integer")

    rng = Random(seed)
    means = []
    for _ in range(simulations):
        resampled = []
        while len(resampled) < n:
            start = rng.randrange(n)
            resampled.extend(values[(start + offset) % n] for offset in range(block_size))
        row = resampled[:n]
        means.append(sum(row) / n)

    ordered = tuple(sorted(means))
    tail = (1.0 - level) / 2.0
    summary = BlockBootstrapSummary(
        n, block_size, simulations, level, sum(values) / n, float(median(ordered)),
        _quantile(ordered, tail), _quantile(ordered, 1.0 - tail),
        sum(value <= 0.0 for value in ordered) / simulations * 100.0,
    )
    summary.validate()
    return summary
