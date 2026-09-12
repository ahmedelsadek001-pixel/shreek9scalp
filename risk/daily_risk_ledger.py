"""Fail-closed daily realized-risk ledger for SHREEK V5.1."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from math import isfinite
from typing import Dict


@dataclass
class DailyRiskLedger:
    """Track realized PnL by UTC trading date and enforce a loss budget."""

    starting_equity: float
    max_daily_loss_pct: float = 0.05
    _realized_by_day: Dict[date, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isfinite(self.starting_equity) or self.starting_equity <= 0:
            raise ValueError("starting_equity must be positive and finite")
        if not isfinite(self.max_daily_loss_pct) or not 0 < self.max_daily_loss_pct <= 1:
            raise ValueError("max_daily_loss_pct must be in (0, 1]")

    @property
    def max_daily_loss(self) -> float:
        return self.starting_equity * self.max_daily_loss_pct

    def realized(self, day: date) -> float:
        return self._realized_by_day.get(day, 0.0)

    def record(self, day: date, pnl: float) -> None:
        if not isinstance(day, date):
            raise TypeError("day must be a date")
        if not isfinite(float(pnl)):
            raise ValueError("pnl must be finite")
        self._realized_by_day[day] = self.realized(day) + float(pnl)

    def loss_used(self, day: date) -> float:
        return max(0.0, -self.realized(day))

    def loss_remaining(self, day: date) -> float:
        return max(0.0, self.max_daily_loss - self.loss_used(day))

    def can_open(self, day: date, modeled_loss: float = 0.0) -> bool:
        if not isfinite(float(modeled_loss)) or modeled_loss < 0:
            return False
        return self.loss_remaining(day) >= float(modeled_loss)

    def require_can_open(self, day: date, modeled_loss: float = 0.0) -> None:
        if not self.can_open(day, modeled_loss):
            raise RuntimeError("daily risk budget exhausted or invalid")
