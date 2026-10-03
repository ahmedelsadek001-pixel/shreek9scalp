"""Fail-closed operational readiness checks for SHREEK V5.3.

The guard evaluates an externally supplied environment snapshot. It never
connects to a broker, sends orders, or changes positions.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite


@dataclass(frozen=True)
class OperationalPolicy:
    max_quote_age_seconds: float = 5.0
    max_clock_skew_seconds: float = 2.0
    require_heartbeat: bool = True

    def validate(self) -> None:
        values = (self.max_quote_age_seconds, self.max_clock_skew_seconds)
        if any(type(value) not in (int, float) for value in values):
            raise ValueError(
                "operational timing limits must be built-in int or float numbers")
        try:
            finite = all(isfinite(value) for value in values)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(
                "operational timing limits must be finite") from exc
        if not finite:
            raise ValueError("operational timing limits must be finite")
        if any(value < 0 for value in values):
            raise ValueError("operational timing limits must be non-negative")
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
    *,
    now: datetime | None = None,
) -> tuple[bool, tuple[str, ...]]:
    """Evaluate operational readiness without granting execution authority."""
    if type(policy) is not OperationalPolicy:
        raise TypeError(
            "operational policy must be exact OperationalPolicy")
    policy.validate()
    if not isinstance(snapshot, OperationalSnapshot):
        raise TypeError("snapshot must be OperationalSnapshot")
    if type(snapshot.connected) is not bool or type(snapshot.trading_enabled) is not bool:
        return False, ("connected and trading_enabled must be boolean",)
    if now is not None and (
        not isinstance(now, datetime)
        or now.tzinfo is None
        or now.utcoffset() is None
    ):
        raise ValueError("now must be timezone-aware")

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

    reference_time = snapshot.observed_at if now is None else now
    if now is not None:
        observation_age = (now - snapshot.observed_at).total_seconds()
        if observation_age < -policy.max_clock_skew_seconds:
            reasons.append("environment observation is ahead of evaluation")
        elif observation_age > policy.max_quote_age_seconds:
            reasons.append("environment observation is stale")

    quote_age = (reference_time - snapshot.quote_time).total_seconds()
    if quote_age < -policy.max_clock_skew_seconds:
        reasons.append("quote timestamp is ahead of observation")
    elif quote_age > policy.max_quote_age_seconds:
        reasons.append("quote is stale")

    if policy.require_heartbeat:
        if snapshot.heartbeat_at is None:
            reasons.append("heartbeat missing")
        else:
            heartbeat_age = (reference_time - snapshot.heartbeat_at).total_seconds()
            if heartbeat_age < -policy.max_clock_skew_seconds:
                reasons.append("heartbeat timestamp is ahead of observation")
            elif heartbeat_age > policy.max_quote_age_seconds:
                reasons.append("heartbeat is stale")
    return not reasons, tuple(reasons)
