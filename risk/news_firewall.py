"""Causal high-impact-news firewall for trade admission."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import IntEnum
from typing import FrozenSet, Iterable


class NewsImpact(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3


@dataclass(frozen=True)
class NewsEvent:
    timestamp: datetime
    impact: NewsImpact
    currencies: FrozenSet[str] = frozenset()
    title: str = ""

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("news timestamp must be timezone-aware")
        if not isinstance(self.impact, NewsImpact):
            raise TypeError("impact must be NewsImpact")
        normalized = frozenset(value.strip().upper() for value in self.currencies)
        if any(not value for value in normalized):
            raise ValueError("news currencies must be non-empty strings")
        object.__setattr__(self, "currencies", normalized)


@dataclass(frozen=True)
class NewsFirewallPolicy:
    before_minutes: int = 15
    after_minutes: int = 15
    minimum_impact: NewsImpact = NewsImpact.HIGH

    def __post_init__(self) -> None:
        if isinstance(self.before_minutes, bool) or self.before_minutes < 0:
            raise ValueError("before_minutes must be non-negative")
        if isinstance(self.after_minutes, bool) or self.after_minutes < 0:
            raise ValueError("after_minutes must be non-negative")
        if not isinstance(self.minimum_impact, NewsImpact):
            raise TypeError("minimum_impact must be NewsImpact")

    def blocked(self, timestamp: datetime, events: Iterable[NewsEvent], currencies: Iterable[str] = ()) -> bool:
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("check timestamp must be timezone-aware")
        symbols = frozenset(value.strip().upper() for value in currencies)
        if any(not value for value in symbols):
            raise ValueError("currencies must be non-empty strings")
        for event in events:
            if event.impact < self.minimum_impact:
                continue
            if event.currencies and symbols and event.currencies.isdisjoint(symbols):
                continue
            if event.currencies and not symbols:
                continue
            start = event.timestamp - timedelta(minutes=self.before_minutes)
            end = event.timestamp + timedelta(minutes=self.after_minutes)
            if start <= timestamp <= end:
                return True
        return False

    def require_clear(self, timestamp: datetime, events: Iterable[NewsEvent], currencies: Iterable[str] = ()) -> None:
        if self.blocked(timestamp, events, currencies):
            raise RuntimeError("high-impact news firewall active")
