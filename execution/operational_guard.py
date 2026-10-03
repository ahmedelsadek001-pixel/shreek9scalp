"""Fail-closed operational readiness checks for SHREEK V5.3.

The guard evaluates an externally supplied environment snapshot. It never
connects to a broker, sends orders, or changes positions.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite


def _utc_snapshot(value: object) -> datetime | None:
    """Copy an aware timestamp without retaining caller-owned timezone state."""
    if not isinstance(value, datetime):
        return None
    try:
        if value.tzinfo is None:
            return None
        offset = value.utcoffset()
        if offset is None:
            return None
        wall_time = datetime(
            value.year, value.month, value.day,
            value.hour, value.minute, value.second, value.microsecond,
            fold=value.fold,
        )
        return (wall_time - offset).replace(tzinfo=timezone.utc)
    except Exception:
        return None


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
    if type(snapshot) is not OperationalSnapshot:
        raise TypeError(
            "snapshot must be OperationalSnapshot (exact type required)")
    connected = snapshot.connected
    trading_enabled = snapshot.trading_enabled
    observed_at = _utc_snapshot(snapshot.observed_at)
    quote_time = _utc_snapshot(snapshot.quote_time)
    heartbeat_value = snapshot.heartbeat_at
    heartbeat_supplied = heartbeat_value is not None
    heartbeat_at = _utc_snapshot(heartbeat_value)
    if type(connected) is not bool or type(trading_enabled) is not bool:
        return False, ("connected and trading_enabled must be boolean",)
    now_utc = None if now is None else _utc_snapshot(now)
    if now is not None and now_utc is None:
        raise ValueError("now must be timezone-aware")

    reasons: list[str] = []
    if observed_at is None or quote_time is None:
        return False, ("observed_at and quote_time must be timezone-aware",)
    if heartbeat_supplied and heartbeat_at is None:
        reasons.append("heartbeat timestamp must be timezone-aware")
    if not connected:
        reasons.append("environment disconnected")
    if not trading_enabled:
        reasons.append("trading disabled")

    reference_time = observed_at if now_utc is None else now_utc
    if now is not None:
        observation_age = (now_utc - observed_at).total_seconds()
        if observation_age < -policy.max_clock_skew_seconds:
            reasons.append("environment observation is ahead of evaluation")
        elif observation_age > policy.max_quote_age_seconds:
            reasons.append("environment observation is stale")

    quote_age = (reference_time - quote_time).total_seconds()
    if quote_age < -policy.max_clock_skew_seconds:
        reasons.append("quote timestamp is ahead of observation")
    elif quote_age > policy.max_quote_age_seconds:
        reasons.append("quote is stale")

    if policy.require_heartbeat:
        if not heartbeat_supplied:
            reasons.append("heartbeat missing")
        elif heartbeat_at is not None:
            heartbeat_age = (reference_time - heartbeat_at).total_seconds()
            if heartbeat_age < -policy.max_clock_skew_seconds:
                reasons.append("heartbeat timestamp is ahead of observation")
            elif heartbeat_age > policy.max_quote_age_seconds:
                reasons.append("heartbeat is stale")
    return not reasons, tuple(reasons)
