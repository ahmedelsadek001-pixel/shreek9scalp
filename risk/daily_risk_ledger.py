"""Fail-closed daily realized-risk ledger for SHREEK V5.1."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from math import isfinite
from typing import Dict


def _finite_float(value: object, field_name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field_name} must be finite") from exc
    if not isfinite(result):
        raise ValueError(f"{field_name} must be finite")
    return result


@dataclass
class DailyRiskLedger:
    """Track realized PnL by trading date and enforce a loss budget."""

    starting_equity: float
    max_daily_loss_pct: float = 0.05
    _realized_by_day: Dict[date, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.starting_equity = _finite_float(self.starting_equity, "starting_equity")
        self.max_daily_loss_pct = _finite_float(self.max_daily_loss_pct, "max_daily_loss_pct")
        if self.starting_equity <= 0:
            raise ValueError("starting_equity must be positive and finite")
        if not 0 < self.max_daily_loss_pct <= 1:
            raise ValueError("max_daily_loss_pct must be in (0, 1]")
        if not isfinite(self.max_daily_loss):
            raise ValueError("maximum daily loss must be finite")

    @property
    def max_daily_loss(self) -> float:
        return self.starting_equity * self.max_daily_loss_pct

    @staticmethod
    def _valid_day(day: object) -> bool:
        return isinstance(day, date) and not isinstance(day, datetime)

    def realized(self, day: date) -> float:
        if not self._valid_day(day):
            raise TypeError("day must be a date, not a datetime")
        return self._realized_by_day.get(day, 0.0)

    def record(self, day: date, pnl: float) -> None:
        if not self._valid_day(day):
            raise TypeError("day must be a date, not a datetime")
        normalized_pnl = _finite_float(pnl, "pnl")
        updated = self.realized(day) + normalized_pnl
        if not isfinite(updated):
            raise ValueError("cumulative realized pnl must be finite")
        self._realized_by_day[day] = updated

    def loss_used(self, day: date) -> float:
        return max(0.0, -self.realized(day))

    def loss_remaining(self, day: date) -> float:
        return max(0.0, self.max_daily_loss - self.loss_used(day))

    def can_open(self, day: date, modeled_loss: float = 0.0) -> bool:
        if not self._valid_day(day):
            return False
        try:
            normalized_loss = _finite_float(modeled_loss, "modeled_loss")
        except ValueError:
            return False
        if normalized_loss < 0:
            return False
        return self.loss_remaining(day) >= normalized_loss

    def require_can_open(self, day: date, modeled_loss: float = 0.0) -> None:
        if not self.can_open(day, modeled_loss):
            raise RuntimeError("daily risk budget exhausted or invalid")
