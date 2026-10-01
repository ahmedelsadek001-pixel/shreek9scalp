"""Statistical uncertainty helpers for SHREEK research evidence.

These functions quantify sampling uncertainty without granting release or
execution authority. They are deterministic and operate only on realized,
finite trade PnL observations.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from statistics import NormalDist
from typing import Iterable


@dataclass(frozen=True)
class MeanConfidenceInterval:
    samples: int
    mean: float
    standard_error: float
    confidence: float
    lower: float
    upper: float

    def validate(self) -> None:
        values = (self.mean, self.standard_error, self.confidence, self.lower, self.upper)
        if type(self.samples) is not int or self.samples < 2:
            raise ValueError("at least two samples are required")
        if not all(isfinite(float(value)) for value in values):
            raise ValueError("confidence interval values must be finite")
        if not 0.0 < self.confidence < 1.0:
            raise ValueError("confidence must be between zero and one")
        if self.standard_error < 0 or self.lower > self.upper:
            raise ValueError("invalid confidence interval")


def _finite_pnl(values: Iterable[float]) -> tuple[float, ...]:
    try:
        sample = tuple(values)
    except TypeError as exc:
        raise ValueError("pnl must be iterable") from exc
    if len(sample) < 2:
        raise ValueError("at least two pnl observations are required")
    normalized = []
    for value in sample:
        if isinstance(value, bool):
            raise ValueError("pnl observations must be finite numbers")
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("pnl observations must be finite numbers") from exc
        if not isfinite(number):
            raise ValueError("pnl observations must be finite numbers")
        normalized.append(number)
    return tuple(normalized)


def mean_confidence_interval(pnl: Iterable[float], confidence: float = 0.95) -> MeanConfidenceInterval:
    """Return a normal-approximation CI for mean realized trade PnL.

    This is an uncertainty diagnostic, not proof of profitability. For small,
    dependent, or regime-clustered samples the caller should prefer block
    bootstrap / independent OOS evidence before making a release decision.
    """
    if isinstance(confidence, bool):
        raise ValueError("confidence must be numeric")
    try:
        level = float(confidence)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("confidence must be numeric") from exc
    if not isfinite(level) or not 0.0 < level < 1.0:
        raise ValueError("confidence must be between zero and one")

    sample = _finite_pnl(pnl)
    n = len(sample)
    avg = sum(sample) / n
    variance = sum((value - avg) ** 2 for value in sample) / (n - 1)
    standard_error = sqrt(variance / n)
    z_score = NormalDist().inv_cdf(0.5 + level / 2.0)
    margin = z_score * standard_error
    result = MeanConfidenceInterval(n, avg, standard_error, level, avg - margin, avg + margin)
    result.validate()
    return result


def confidence_excludes_zero(interval: MeanConfidenceInterval) -> bool:
    """Return True only when the complete interval lies on one side of zero."""
    if not isinstance(interval, MeanConfidenceInterval):
        raise ValueError("interval must be MeanConfidenceInterval")
    interval.validate()
    return interval.lower > 0.0 or interval.upper < 0.0
