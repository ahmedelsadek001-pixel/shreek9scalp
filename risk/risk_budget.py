"""Deterministic position-risk budgeting for SHREEK V5.1.

This module calculates maximum modeled loss and position volume. It has no
broker or execution authority and fails closed on invalid inputs.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Optional


@dataclass(frozen=True)
class RiskBudget:
    equity: float
    risk_pct: float = 0.01
    max_risk_amount: Optional[float] = None

    def __post_init__(self) -> None:
        if not isfinite(self.equity) or self.equity <= 0:
            raise ValueError("equity must be positive and finite")
        if not isfinite(self.risk_pct) or not 0 < self.risk_pct <= 1:
            raise ValueError("risk_pct must be in (0, 1]")
        if self.max_risk_amount is not None and (
            not isfinite(self.max_risk_amount) or self.max_risk_amount <= 0
        ):
            raise ValueError("max_risk_amount must be positive and finite")

    @property
    def risk_amount(self) -> float:
        calculated = self.equity * self.risk_pct
        return min(calculated, self.max_risk_amount) if self.max_risk_amount is not None else calculated

    def modeled_loss(self, entry: float, stop: float, volume: float, point_value: float = 1.0) -> float:
        self._validate_trade_values(entry, stop, volume, point_value)
        return abs(float(entry) - float(stop)) * float(volume) * float(point_value)

    def allows(self, entry: float, stop: float, volume: float, point_value: float = 1.0) -> bool:
        return self.modeled_loss(entry, stop, volume, point_value) <= self.risk_amount + 1e-12

    def size_for_stop(self, entry: float, stop: float, point_value: float = 1.0) -> float:
        if not isfinite(float(entry)) or not isfinite(float(stop)) or entry <= 0 or stop <= 0:
            raise ValueError("entry and stop must be positive and finite")
        if not isfinite(float(point_value)) or point_value <= 0:
            raise ValueError("point_value must be positive and finite")
        distance = abs(float(entry) - float(stop))
        if distance <= 0:
            raise ValueError("entry and stop must differ")
        return self.risk_amount / (distance * float(point_value))

    @staticmethod
    def _validate_trade_values(entry: float, stop: float, volume: float, point_value: float) -> None:
        values = (entry, stop, volume, point_value)
        if not all(isfinite(float(value)) for value in values):
            raise ValueError("trade risk inputs must be finite")
        if entry <= 0 or stop <= 0 or volume <= 0 or point_value <= 0:
            raise ValueError("trade risk inputs must be positive")
        if entry == stop:
            raise ValueError("entry and stop must differ")
