"""Deterministic research metrics for recorded trade outcomes."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from statistics import mean, stdev
from typing import Iterable


@dataclass(frozen=True)
class PerformanceMetrics:
    samples: int
    net_pnl: float
    expectancy: float
    win_rate: float
    profit_factor: float
    payoff_ratio: float
    max_consecutive_losses: int
    sqn: float


def calculate_metrics(pnl: Iterable[float]) -> PerformanceMetrics:
    """Calculate deterministic trade-level performance metrics from net PnL."""
    values = [float(value) for value in pnl]
    if not values:
        raise ValueError("at least one trade outcome is required")
    if any(not isfinite(value) for value in values):
        raise ValueError("trade outcomes must be finite")

    wins = [value for value in values if value > 0]
    losses = [-value for value in values if value < 0]
    gross_profit = sum(wins)
    gross_loss = sum(losses)
    win_rate = len(wins) / len(values) * 100.0
    profit_factor = gross_profit / gross_loss if gross_loss else float("inf")
    payoff = mean(wins) / mean(losses) if wins and losses else float("inf") if wins else 0.0
    max_streak = 0
    streak = 0
    for value in values:
        if value < 0:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    deviation = stdev(values) if len(values) > 1 else 0.0
    sqn = mean(values) / deviation * sqrt(len(values)) if deviation > 0 else 0.0
    net = sum(values)
    return PerformanceMetrics(
        len(values),
        net,
        mean(values),
        win_rate,
        profit_factor,
        payoff,
        max_streak,
        sqn,
    )
