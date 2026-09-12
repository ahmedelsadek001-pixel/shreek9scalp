"""Deterministic, research-only market regime classification for SHREEK V5.2.

The classifier is intentionally explainable and execution-free. It uses only
closed OHLC observations and labels each window as TREND, RANGE, or UNKNOWN.
It must not authorize, size, or route trades.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Sequence


class Regime(str, Enum):
    TREND = "TREND"
    RANGE = "RANGE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RegimeConfig:
    lookback: int = 20
    trend_efficiency_min: float = 0.55
    range_efficiency_max: float = 0.30

    def validate(self) -> None:
        if self.lookback < 2:
            raise ValueError("lookback must be at least 2")
        if not 0 < self.range_efficiency_max < self.trend_efficiency_min <= 1:
            raise ValueError("efficiency thresholds are inconsistent")


def classify_regime(closes: Sequence[float], config: RegimeConfig = RegimeConfig()) -> Regime:
    """Classify the latest closed-price window using directional efficiency.

    Efficiency = absolute net displacement / sum of absolute bar-to-bar moves.
    High efficiency indicates directional movement; low efficiency indicates
    choppy/ranging movement. Insufficient or invalid data returns UNKNOWN.
    """
    config.validate()
    if len(closes) < config.lookback:
        return Regime.UNKNOWN
    window = closes[-config.lookback :]
    if any(not isfinite(float(value)) for value in window):
        return Regime.UNKNOWN
    path = sum(abs(float(b) - float(a)) for a, b in zip(window, window[1:]))
    displacement = abs(float(window[-1]) - float(window[0]))
    if path <= 0:
        return Regime.RANGE
    efficiency = displacement / path
    if efficiency >= config.trend_efficiency_min:
        return Regime.TREND
    if efficiency <= config.range_efficiency_max:
        return Regime.RANGE
    return Regime.UNKNOWN
