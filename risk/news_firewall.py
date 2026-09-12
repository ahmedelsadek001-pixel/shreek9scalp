"""Deterministic high-impact-news firewall for trade admission."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import IntEnum
from typing import Iterable


class NewsImpact(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3


@dataclass(frozen=True)
class NewsEvent:
    timestamp: datetime
    impact: NewsImpact
    currencies: frozenset[str] = frozenset()
    title: str = ""

    def validate(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("news timestamp must be timezone-aware")
        if not isinstance(self.impact, NewsImpact):
            raise ValueError("impact must be NewsImpact")
        if any(not isinstance(currency, str) or not currency.strip() for currency in self.currencies):
            raise ValueError("news currencies must be non-empty strings")


@dataclass(frozen=True)
class NewsFirewallPolicy:
    """Block high-impact events in an explicit before/after window."""

    before_minutes: int = 15
    after_minutes: int = 15
    minimum_impact: NewsImpact = NewsImpact.HIGH

    def __post_init__(self) -> None:
        if isinstance(self.before_minutes, bool) or self.before_minutes < 0:
            raise ValueError("before_minutes must be non-negative")
        if isinstance(self.after_minutes, bool) or self.after_minutes < 0:
            raise ValueError("after_minutes must be non-negative")
        if not isinstance(self.minimum_impact, NewsImpact):
            raise ValueError("minimum_impact must be NewsImpact")

    def blocked(self, timestamp: datetime, events: Iterable[NewsEvent], currencies: Iterable[str] = ()) -> bool:
        if timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        wanted = {currency.strip().upper() for currency in currencies if currency.strip()}
        before = timedelta(minutes=self.before_minutes)
        after = timedelta(minutes=self.after_minutes)
        for event in events:
            event.validate()
            if event.impact < self.minimum_impact:
                continue
            if wanted and event.currencies and wanted.isdisjoint({c.upper() for c in event.currencies}):
                continue
            if event.timestamp - before <= timestamp <= event.timestamp + after:
                return True
        return False

    def require_clear(self, timestamp: datetime, events: Iterable[NewsEvent], currencies: Iterable[str] = ()) -> None:
        if self.blocked(timestamp, events, currencies):
            raise RuntimeError("high-impact news firewall active")
