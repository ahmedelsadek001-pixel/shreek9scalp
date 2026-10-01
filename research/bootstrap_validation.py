"""Deterministic bootstrap confidence analysis for SHREEK V5.2 research."""
from __future__ import annotations

from dataclasses import dataclass
import random
from math import isfinite
from statistics import mean
from typing import Sequence


@dataclass(frozen=True)
class BootstrapReport:
    samples: int
    simulations: int
    seed: int
    observed_expectancy: float
    lower_ci: float
    upper_ci: float
    positive_expectancy_probability: float

    @property
    def confidence_contains_zero(self) -> bool:
        return self.lower_ci <= 0.0 <= self.upper_ci


def validate_bootstrap_input(values: Sequence[float], simulations: int) -> None:
    if len(values) < 2:
        raise ValueError("at least two trade outcomes are required")
    if any(not isfinite(float(value)) for value in values):
        raise ValueError("trade outcomes must be finite")
    if simulations < 100:
        raise ValueError("simulations must be at least 100")


def bootstrap_expectancy(
    pnl: Sequence[float],
    *,
    simulations: int = 2000,
    seed: int = 42,
    confidence: float = 0.95,
) -> BootstrapReport:
    """Estimate a percentile bootstrap CI for mean trade PnL deterministically."""
    values = tuple(float(value) for value in pnl)
    validate_bootstrap_input(values, simulations)
    if not 0 < confidence < 1 or not isfinite(float(confidence)):
        raise ValueError("confidence must be between 0 and 1")
    rng = random.Random(seed)
    size = len(values)
    means = sorted(mean(rng.choices(values, k=size)) for _ in range(simulations))
    alpha = (1.0 - confidence) / 2.0

    def percentile(fraction: float) -> float:
        index = (len(means) - 1) * fraction
        low = int(index)
        high = min(low + 1, len(means) - 1)
        weight = index - low
        return means[low] + (means[high] - means[low]) * weight

    positive_probability = sum(value > 0 for value in means) / len(means)
    return BootstrapReport(
        samples=size,
        simulations=simulations,
        seed=seed,
        observed_expectancy=mean(values),
        lower_ci=percentile(alpha),
        upper_ci=percentile(1.0 - alpha),
        positive_expectancy_probability=positive_probability,
    )
