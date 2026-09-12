"""Strict signal admission pipeline for SHREEK V5.1.

A signal is not a trade. This module composes deterministic gates and
returns an immutable admission decision. It never sends orders or performs
network I/O.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Callable, Iterable

from core.enums import Direction, SignalStatus
from core.models import TradeSignal
from risk.trade_gates import GateResult


@dataclass(frozen=True)
class AdmissionDecision:
    allowed: bool
    reason: str
    signal: TradeSignal | None = None
    failed_gate: str | None = None


def admit_signal(
    signal: TradeSignal | None,
    gates: Iterable[tuple[str, Callable[[], GateResult]]],
) -> AdmissionDecision:
    """Admit only a fully aligned, valid BUY/SELL signal that passes every gate.

    Gate evaluation is ordered and short-circuits on the first failure.
    Missing signals, invalid status, RANGE/UNKNOWN directions, misalignment,
    and non-finite or invalid prices fail closed.
    """
    if signal is None:
        return AdmissionDecision(False, "signal unavailable")
    if signal.status != SignalStatus.VALID:
        return AdmissionDecision(False, "signal status is not VALID")
    if signal.direction not in (Direction.BUY, Direction.SELL):
        return AdmissionDecision(False, "direction is not executable")
    if not signal.aligned:
        return AdmissionDecision(False, "signal is not aligned with higher-timeframe direction")
    if not all(isfinite(float(value)) for value in (signal.entry_price, signal.sl_price)):
        return AdmissionDecision(False, "entry/stop price is not finite")
    if signal.entry_price <= 0 or signal.sl_price <= 0:
        return AdmissionDecision(False, "invalid entry/stop price")
    if signal.direction == Direction.BUY and signal.sl_price >= signal.entry_price:
        return AdmissionDecision(False, "BUY stop must be below entry")
    if signal.direction == Direction.SELL and signal.sl_price <= signal.entry_price:
        return AdmissionDecision(False, "SELL stop must be above entry")

    for name, gate in gates:
        result = gate()
        if not result.allowed:
            return AdmissionDecision(False, result.reason, signal, name)
    return AdmissionDecision(True, "all signal admission gates passed", signal)
