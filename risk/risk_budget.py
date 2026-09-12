"""Account-level risk budget calculations independent of broker runtime."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class RiskBudget:
    equity: float
    risk_pct: float
    daily_loss: float = 0.0
    daily_loss_limit_pct: float = 0.05

    @property
    def amount(self) -> float:
        values = (self.equity, self.risk_pct, self.daily_loss, self.daily_loss_limit_pct)
        if any(not isfinite(float(value)) for value in values):
            raise ValueError("risk budget inputs must be finite")
        if self.equity <= 0 or self.risk_pct <= 0 or self.daily_loss_limit_pct <= 0:
            raise ValueError("equity and risk percentages must be positive")
        if self.risk_pct > self.daily_loss_limit_pct:
            raise ValueError("per-trade risk cannot exceed daily loss limit")
        remaining_daily = self.equity * self.daily_loss_limit_pct + self.daily_loss
        if remaining_daily <= 0:
            return 0.0
        return min(self.equity * self.risk_pct, remaining_daily)
