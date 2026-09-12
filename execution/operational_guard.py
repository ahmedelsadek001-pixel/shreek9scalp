"""Fail-closed operational readiness checks for SHREEK V5.3.

The guard evaluates an externally supplied environment snapshot. It never
connects to a broker, sends orders, or changes positions.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite


@dataclass(frozen=True)
class OperationalPolicy:
    max_quote_age_seconds: float = 5.0
    max_clock_skew_seconds: float = 2.0
    require_heartbeat: bool = True

    def validate(self) -> None:
        values = (self.max_quote_age_seconds, self.max_clock_skew_seconds)
        if any(not isfinite(float(value)) or float(value) < 0 for value in values):
            raise ValueError("operational timing limits must be finite and non-negative")
        if type(self.require_heartbeat) is not bool:
            raise ValueError("require_heartbeat must be boolean")


@dataclass(frozen=True)
class OperationalSnapshot:
    observed_at: datetime
    quote_time: datetime
    heartbeat_at: datetime | None
    connected: bool
    trading_enabled: bool


def evaluate_operational_readiness(
    policy: OperationalPolicy,
    snapshot: OperationalSnapshot,
) -> tuple[bool, tuple[str, ...]]:
    """Evaluate operational readiness without granting execution authority."""
    policy.validate()
    if not isinstance(snapshot, OperationalSnapshot):
        raise TypeError("snapshot must be OperationalSnapshot")
    reasons: list[str] = []
    timestamps = (snapshot.observed_at, snapshot.quote_time)
    if any(not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None for value in timestamps):
        return False, ("observed_at and quote_time must be timezone-aware",)
    if snapshot.heartbeat_at is not None and (
        not isinstance(snapshot.heartbeat_at, datetime)
        or snapshot.heartbeat_at.tzinfo is None
        or snapshot.heartbeat_at.utcoffset() is None
    ):
        reasons.append("heartbeat timestamp must be timezone-aware")
    if not snapshot.connected:
        reasons.append("environment disconnected")
    if not snapshot.trading_enabled:
        reasons.append("trading disabled")

    quote_age = (snapshot.observed_at - snapshot.quote_time).total_seconds()
    if quote_age < -policy.max_clock_skew_seconds:
        reasons.append("quote timestamp is ahead of observation")
    elif quote_age > policy.max_quote_age_seconds:
        reasons.append("quote is stale")

    if policy.require_heartbeat:
        if snapshot.heartbeat_at is None:
            reasons.append("heartbeat missing")
        else:
            heartbeat_age = (snapshot.observed_at - snapshot.heartbeat_at).total_seconds()
            if heartbeat_age < -policy.max_clock_skew_seconds:
                reasons.append("heartbeat timestamp is ahead of observation")
            elif heartbeat_age > policy.max_quote_age_seconds:
                reasons.append("heartbeat is stale")
    return not reasons, tuple(reasons)
