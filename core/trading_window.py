"""Causal trading-window and holding-period policies.

Pure policy helpers: no broker I/O and no order authority. All timestamps are
expected to already be normalized to the strategy's configured timezone.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from math import isfinite
from typing import Optional


@dataclass(frozen=True)
class SessionWindow:
    name: str
    start: time
    end: time
    weekdays: frozenset[int] = frozenset({0, 1, 2, 3, 4})

    def contains(self, timestamp: datetime) -> bool:
        if timestamp.weekday() not in self.weekdays:
            return False
        current = timestamp.timetz().replace(tzinfo=None)
        if self.start <= self.end:
            return self.start <= current <= self.end
        # Overnight window: e.g. 22:00 -> 02:00.
        return current >= self.start or current <= self.end


@dataclass(frozen=True)
class TradingWindowPolicy:
    sessions: tuple[SessionWindow, ...] = ()
    max_holding_minutes: Optional[int] = None
    allow_weekend: bool = False

    def validate(self) -> None:
        if self.max_holding_minutes is not None and self.max_holding_minutes <= 0:
            raise ValueError("max_holding_minutes must be positive")
        for session in self.sessions:
            if not session.name.strip():
                raise ValueError("session name must not be empty")
            if not session.weekdays or any(day < 0 or day > 6 for day in session.weekdays):
                raise ValueError("session weekdays must be in 0..6")
        if not isinstance(self.allow_weekend, bool):
            raise ValueError("allow_weekend must be boolean")

    def is_open(self, timestamp: datetime) -> bool:
        self.validate()
        if not self.allow_weekend and timestamp.weekday() >= 5:
            return False
        return not self.sessions or any(session.contains(timestamp) for session in self.sessions)

    def holding_expired(self, entry_time: datetime, timestamp: datetime) -> bool:
        self.validate()
        if timestamp < entry_time:
            raise ValueError("timestamp cannot precede entry_time")
        if self.max_holding_minutes is None:
            return False
        return timestamp >= entry_time + timedelta(minutes=self.max_holding_minutes)
