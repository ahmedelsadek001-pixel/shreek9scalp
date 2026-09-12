"""Research-only execution-quality analytics for SHREEK V5.3."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from statistics import median
from typing import Sequence


@dataclass(frozen=True)
class ExecutionQualityReport:
    samples: int
    mean_slippage: float
    median_slippage: float
    max_abs_slippage: float
    mean_spread: float
    max_spread: float


def analyze_execution_quality(
    expected_prices: Sequence[float],
    fill_prices: Sequence[float],
    spreads: Sequence[float] = (),
) -> ExecutionQualityReport:
    """Measure realized price deviation and spread; never sends an order."""
    if len(expected_prices) != len(fill_prices):
        raise ValueError("expected_prices and fill_prices must have equal length")
    if not expected_prices:
        raise ValueError("at least one execution sample is required")
    if spreads and len(spreads) != len(expected_prices):
        raise ValueError("spreads must align with execution samples")
    if any(not isfinite(float(x)) or float(x) <= 0 for x in (*expected_prices, *fill_prices)):
        raise ValueError("prices must be finite and positive")
    if spreads and any(not isfinite(float(x)) or float(x) < 0 for x in spreads):
        raise ValueError("spreads must be finite and non-negative")
    slippage = [float(fill) - float(expected) for expected, fill in zip(expected_prices, fill_prices)]
    spread_values = [float(x) for x in spreads] if spreads else [0.0] * len(slippage)
    return ExecutionQualityReport(
        len(slippage),
        sum(slippage) / len(slippage),
        median(slippage),
        max(abs(x) for x in slippage),
        sum(spread_values) / len(spread_values),
        max(spread_values),
    )
