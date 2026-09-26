"""Fail-closed pre-trade gates for V5.1.

These gates decide whether a validated signal is eligible for execution.
They never create a signal and never send an order.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Optional


@dataclass(frozen=True)
class GateResult:
    allowed: bool
    reason: str


def spread_gate(spread_points: Optional[float], max_spread_points: float) -> GateResult:
    if spread_points is None or max_spread_points <= 0:
        return GateResult(False, "spread data unavailable or limit invalid")
    if not isfinite(spread_points) or spread_points < 0:
        return GateResult(False, "invalid spread")
    if spread_points > max_spread_points:
        return GateResult(False, "spread exceeds configured maximum")
    return GateResult(True, "spread acceptable")


def volatility_gate(atr: Optional[float], min_atr: float, max_atr: float) -> GateResult:
    if atr is None or not isfinite(atr) or atr <= 0:
        return GateResult(False, "ATR unavailable or invalid")
    if min_atr < 0 or max_atr <= 0 or min_atr > max_atr:
        return GateResult(False, "invalid ATR limits")
    if atr < min_atr:
        return GateResult(False, "volatility below minimum")
    if atr > max_atr:
        return GateResult(False, "volatility above maximum")
    return GateResult(True, "volatility acceptable")


def daily_loss_gate(daily_pnl: float, max_daily_loss: float) -> GateResult:
    if not isfinite(daily_pnl) or max_daily_loss <= 0:
        return GateResult(False, "invalid daily-loss state")
    if daily_pnl <= -abs(max_daily_loss):
        return GateResult(False, "daily loss limit reached")
    return GateResult(True, "daily loss limit not reached")


def cooldown_gate(cooldown_active: bool) -> GateResult:
    if cooldown_active:
        return GateResult(False, "post-loss cooldown active")
    return GateResult(True, "cooldown clear")


def duplicate_gate(duplicate: bool) -> GateResult:
    if duplicate:
        return GateResult(False, "duplicate signal")
    return GateResult(True, "signal identity is new")


def all_gates(*results: GateResult) -> GateResult:
    """Evaluate gates in order and fail closed on the first rejection."""
    for result in results:
        if not result.allowed:
            return result
    return GateResult(True, "all pre-trade gates passed")
