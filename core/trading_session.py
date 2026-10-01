"""Deterministic session and holding-period gates for backtesting/paper trading."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Optional


@dataclass(frozen=True)
class SessionWindow:
    name: str
    start: time
    end: time

    def contains(self, timestamp: datetime) -> bool:
        current = timestamp.time()
        if self.start <= self.end:
            return self.start <= current <= self.end
        return current >= self.start or current <= self.end


@dataclass(frozen=True)
class TradingSessionPolicy:
    windows: tuple[SessionWindow, ...] = ()
    max_holding_minutes: Optional[int] = None
    block_weekends: bool = True

    def validate(self) -> None:
        if self.max_holding_minutes is not None and self.max_holding_minutes <= 0:
            raise ValueError("max_holding_minutes must be positive")
        if any(not w.name.strip() for w in self.windows):
            raise ValueError("session names must be non-empty")

    def allowed(self, timestamp: datetime) -> bool:
        if self.block_weekends and timestamp.weekday() >= 5:
            return False
        return not self.windows or any(w.contains(timestamp) for w in self.windows)

    def holding_expired(self, entry_time: datetime, timestamp: datetime) -> bool:
        if self.max_holding_minutes is None:
            return False
        return timestamp - entry_time >= timedelta(minutes=self.max_holding_minutes)
