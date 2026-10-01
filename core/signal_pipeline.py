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
    """Admit only a fully valid, aligned BUY/SELL signal that passes every gate.

    Gate evaluation is ordered and short-circuits on the first failure.
    Missing signals, invalid status, unaligned signals, RANGE/UNKNOWN
    directions, non-finite prices, and invalid stop placement fail closed.
    """
    if signal is None:
        return AdmissionDecision(False, "signal unavailable")
    if signal.status != SignalStatus.VALID:
        return AdmissionDecision(False, "signal status is not VALID")
    if not signal.aligned:
        return AdmissionDecision(False, "signal is not aligned with higher-timeframe bias", signal, "alignment")
    if signal.direction not in (Direction.BUY, Direction.SELL):
        return AdmissionDecision(False, "direction is not executable")
    try:
        entry, stop = float(signal.entry_price), float(signal.sl_price)
    except (TypeError, ValueError, OverflowError):
        return AdmissionDecision(False, "entry/stop price must be numeric")
    if not all(isfinite(value) for value in (entry, stop)):
        return AdmissionDecision(False, "entry/stop price is not finite")
    if entry <= 0 or stop <= 0:
        return AdmissionDecision(False, "invalid entry/stop price")
    if signal.direction == Direction.BUY and stop >= entry:
        return AdmissionDecision(False, "BUY stop must be below entry")
    if signal.direction == Direction.SELL and stop <= entry:
        return AdmissionDecision(False, "SELL stop must be above entry")

    for name, gate in gates:
        result = gate()
        if not result.allowed:
            return AdmissionDecision(False, result.reason, signal, name)
    return AdmissionDecision(True, "all signal admission gates passed", signal)
