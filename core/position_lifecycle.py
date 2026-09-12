"""Pure position-lifecycle logic for SHREEK V5.1.

Calculates execution actions after a fill. No broker I/O or order authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Optional

from core.models import ExecutionLevels


@dataclass(frozen=True)
class LifecyclePolicy:
    tp1_fraction: float = 0.50
    tp2_fraction: float = 0.25
    tp3_fraction: float = 0.25
    breakeven_after_tp1: bool = True
    breakeven_offset: float = 0.0
    trailing_after_tp2: bool = False
    trailing_distance_r: float = 1.0

    def validate(self) -> None:
        fractions = (self.tp1_fraction, self.tp2_fraction, self.tp3_fraction)
        if any(not isfinite(float(x)) or x <= 0 for x in fractions):
            raise ValueError("TP fractions must be finite and positive")
        if abs(sum(fractions) - 1.0) > 1e-9:
            raise ValueError("TP fractions must sum to 1")
        if not isfinite(self.breakeven_offset) or self.breakeven_offset < 0:
            raise ValueError("breakeven offset must be finite and non-negative")
        if not isfinite(self.trailing_distance_r) or self.trailing_distance_r <= 0:
            raise ValueError("trailing distance must be positive")


@dataclass(frozen=True)
class LifecycleState:
    remaining_volume: float
    closed_tp1: bool = False
    closed_tp2: bool = False
    closed_tp3: bool = False
    breakeven_active: bool = False
    stop_price: Optional[float] = None
    trailing_active: bool = False


@dataclass(frozen=True)
class LifecycleAction:
    kind: str
    volume: float
    price: float
    reason: str


def initial_state(volume: float, levels: ExecutionLevels, policy: LifecyclePolicy = LifecyclePolicy()) -> LifecycleState:
    policy.validate()
    if not isfinite(volume) or volume <= 0:
        raise ValueError("volume must be positive and finite")
    if not isfinite(levels.risk) or levels.risk <= 0:
        raise ValueError("execution levels must contain positive risk")
    return LifecycleState(remaining_volume=volume, stop_price=levels.sl)


def _fraction_volume(remaining: float, original: float, fraction: float) -> float:
    if not isfinite(original) or original <= 0:
        raise ValueError("original volume must be positive and finite")
    return min(remaining, original * fraction)


def tp1_action(state: LifecycleState, original_volume: float, levels: ExecutionLevels, policy: LifecyclePolicy) -> LifecycleAction:
    policy.validate()
    if state.closed_tp1:
        raise ValueError("TP1 already processed")
    volume = _fraction_volume(state.remaining_volume, original_volume, policy.tp1_fraction)
    if volume <= 0:
        raise ValueError("no volume available for TP1")
    return LifecycleAction("PARTIAL_CLOSE", volume, levels.tp1, "TP1 reached")


def after_tp1(state: LifecycleState, levels: ExecutionLevels, policy: LifecyclePolicy, original_volume: float) -> LifecycleState:
    action = tp1_action(state, original_volume, levels, policy)
    stop = state.stop_price
    be = state.breakeven_active
    if policy.breakeven_after_tp1:
        if levels.sl < levels.entry:
            stop = levels.entry + policy.breakeven_offset
        elif levels.sl > levels.entry:
            stop = levels.entry - policy.breakeven_offset
        else:
            raise ValueError("invalid execution levels: stop equals entry")
        be = True
    return LifecycleState(
        state.remaining_volume - action.volume,
        True,
        state.closed_tp2,
        state.closed_tp3,
        be,
        stop,
        state.trailing_active,
    )


def tp2_action(state: LifecycleState, original_volume: float, levels: ExecutionLevels, policy: LifecyclePolicy) -> LifecycleAction:
    policy.validate()
    if not state.closed_tp1 or state.closed_tp2:
        raise ValueError("TP2 requires TP1 and must be processed once")
    volume = _fraction_volume(state.remaining_volume, original_volume, policy.tp2_fraction)
    if volume <= 0:
        raise ValueError("no volume available for TP2")
    return LifecycleAction("PARTIAL_CLOSE", volume, levels.tp2, "TP2 reached")


def after_tp2(state: LifecycleState, original_volume: float, levels: ExecutionLevels, policy: LifecyclePolicy) -> LifecycleState:
    action = tp2_action(state, original_volume, levels, policy)
    return LifecycleState(
        state.remaining_volume - action.volume,
        True,
        True,
        state.closed_tp3,
        state.breakeven_active,
        state.stop_price,
        policy.trailing_after_tp2,
    )


def trailing_stop_price(
    state: LifecycleState,
    levels: ExecutionLevels,
    price: float,
    policy: LifecyclePolicy,
    previous_stop: Optional[float] = None,
) -> float:
    """Return a monotonic R-based trailing stop once TP2 has been reached.

    ``previous_stop`` lets stateless callers preserve the stop across bars.
    The backtest engine normally keeps the stop in ``LifecycleState``.
    """
    policy.validate()
    if not state.trailing_active:
        raise ValueError("trailing is not active")
    if not isfinite(price):
        raise ValueError("price must be finite")
    if previous_stop is not None and not isfinite(previous_stop):
        raise ValueError("previous stop must be finite")
    distance = levels.risk * policy.trailing_distance_r
    candidate = price - distance if levels.entry > levels.sl else price + distance
    current = state.stop_price if previous_stop is None else previous_stop
    if current is None:
        return candidate
    return max(current, candidate) if levels.entry > levels.sl else min(current, candidate)


def tp3_action(state: LifecycleState, levels: ExecutionLevels) -> LifecycleAction:
    if not state.closed_tp2 or state.closed_tp3:
        raise ValueError("TP3 requires TP2 and must be processed once")
    if state.remaining_volume <= 0:
        raise ValueError("no volume available for TP3")
    return LifecycleAction("CLOSE_REMAINDER", state.remaining_volume, levels.tp3, "TP3 reached")
