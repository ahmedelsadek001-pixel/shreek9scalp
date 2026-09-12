"""Research-only aggregation of normalized MAE/MFE observations."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from statistics import median
from typing import Iterable

from research.mae_mfe import TradeExcursion


@dataclass(frozen=True)
class ExcursionStats:
    samples: int
    median_mae: float
    median_mfe: float
    p90_mae: float
    p90_mfe: float
    median_mfe_mae_ratio: float


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        raise ValueError("at least one observation is required")
    values = sorted(values)
    index = (len(values) - 1) * fraction
    low = int(index)
    high = min(low + 1, len(values) - 1)
    weight = index - low
    return values[low] + (values[high] - values[low]) * weight


def summarize_excursions(observations: Iterable[TradeExcursion]) -> ExcursionStats:
    """Summarize adverse/favorable excursions without making trading decisions."""
    items = list(observations)
    if not items:
        raise ValueError("at least one excursion observation is required")
    if any(
        not all(isfinite(float(value)) for value in (item.entry, item.exit, item.mae, item.mfe))
        or item.mae < 0
        or item.mfe < 0
        for item in items
    ):
        raise ValueError("excursion observations must be finite and non-negative")
    maes = [float(item.mae) for item in items]
    mfes = [float(item.mfe) for item in items]
    ratios = [mfe / mae for mfe, mae in zip(mfes, maes) if mae > 0]
    return ExcursionStats(
        len(items),
        median(maes),
        median(mfes),
        _percentile(maes, 0.90),
        _percentile(mfes, 0.90),
        median(ratios) if ratios else float("inf"),
    )
