"""Fail-closed broker safety policy for SHREEK V5.3.

This module validates broker/environment facts supplied by an adapter. It does
not connect to a broker and has no order-routing authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class BrokerSafetyPolicy:
    allowed_symbols: frozenset[str]
    max_spread: float
    min_volume: float
    max_volume: float
    max_slippage: float

    def validate(self) -> None:
        if not self.allowed_symbols or any(not symbol.strip() for symbol in self.allowed_symbols):
            raise ValueError("allowed_symbols must contain non-empty symbols")
        values = (self.max_spread, self.min_volume, self.max_volume, self.max_slippage)
        if any(not isfinite(float(value)) for value in values):
            raise ValueError("broker safety limits must be finite")
        if self.max_spread < 0 or self.min_volume <= 0 or self.max_volume < self.min_volume or self.max_slippage < 0:
            raise ValueError("broker safety limits are inconsistent")


def authorize_environment(
    policy: BrokerSafetyPolicy,
    *,
    symbol: str,
    spread: float,
    volume: float,
    slippage: float,
    connected: bool,
    trading_enabled: bool,
) -> tuple[bool, tuple[str, ...]]:
    """Return an authorization decision for a supplied environment snapshot."""
    policy.validate()
    reasons: list[str] = []
    if not connected:
        reasons.append("broker disconnected")
    if not trading_enabled:
        reasons.append("trading disabled")
    if symbol not in policy.allowed_symbols:
        reasons.append("symbol not allowed")
    if not isfinite(spread) or spread < 0 or spread > policy.max_spread:
        reasons.append("spread outside limit")
    if not isfinite(volume) or volume < policy.min_volume or volume > policy.max_volume:
        reasons.append("volume outside limit")
    if not isfinite(slippage) or slippage < 0 or slippage > policy.max_slippage:
        reasons.append("slippage outside limit")
    return not reasons, tuple(reasons)
