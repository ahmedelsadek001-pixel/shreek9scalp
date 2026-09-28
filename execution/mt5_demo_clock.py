"""Explicit DEMO broker clock binding; never infer an offset from a stale tick."""
from __future__ import annotations

from datetime import datetime
from math import isfinite
import os
from typing import Any

from execution.mt5_demo_probe import DemoTerminalConfig


def configured_demo_server_utc_offset_seconds() -> int:
    """Only accept the observed +03:00 broker encoding when opted in locally."""
    raw = os.environ.get("SHREEK_DEMO_SERVER_UTC_OFFSET_SECONDS", "0")
    if raw not in ("0", "10800"):
        raise ValueError("unsupported DEMO server UTC offset")
    return int(raw)


def fresh_demo_quote_age_ms(tick: Any, config: DemoTerminalConfig,
                            now: datetime) -> float | None:
    """Return a bounded quote age, after the explicit server-to-UTC mapping."""
    time_msc = getattr(tick, "time_msc", None)
    offset = getattr(config, "server_utc_offset_seconds", None)
    if (type(time_msc) not in (int, float) or not isfinite(time_msc)
            or type(offset) is not int or offset not in (0, 10800)
            or not isinstance(now, datetime) or now.tzinfo is None
            or now.utcoffset() is None):
        return None
    age = now.timestamp() * 1000 + offset * 1000 - time_msc
    # Explicitly shifted broker timestamps may lead an NTP-synced PC by less
    # than a second. Never allow a whole-second future skew or an old quote.
    future_tolerance_ms = 1000 if offset else 0
    return age if -future_tolerance_ms <= age <= 5000 else None
