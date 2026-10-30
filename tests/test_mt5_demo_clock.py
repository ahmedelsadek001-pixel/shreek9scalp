"""Bounded DEMO-only broker timestamp mapping against a fixed UTC clock."""
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from execution.mt5_demo_clock import (configured_demo_server_utc_offset_seconds,
                                      fresh_demo_quote_age_ms)
from test_mt5_demo_transport import CONFIG


@pytest.mark.parametrize("age_ms, accepted", [
    (-1001, False), (-1000, True), (-300, True), (0, True),
    (5000, True), (5001, False),
])
def test_shifted_broker_tick_has_strict_age_window(age_ms, accepted):
    now = datetime(2026, 9, 28, 5, 0, tzinfo=timezone.utc)
    config = replace(CONFIG, server_utc_offset_seconds=10800)
    timestamp = int(now.timestamp() * 1000) + 10_800_000 - age_ms
    age = fresh_demo_quote_age_ms(SimpleNamespace(time_msc=timestamp), config, now)
    assert (age is not None) is accepted


def test_default_utc_mapping_keeps_zero_future_tolerance():
    now = datetime(2026, 9, 28, 5, 0, tzinfo=timezone.utc)
    timestamp = int(now.timestamp() * 1000)
    assert fresh_demo_quote_age_ms(SimpleNamespace(time_msc=timestamp - 5000), CONFIG, now) == 5000
    assert fresh_demo_quote_age_ms(SimpleNamespace(time_msc=timestamp + 1), CONFIG, now) is None
    assert fresh_demo_quote_age_ms(SimpleNamespace(time_msc=timestamp + 10_800_000), CONFIG, now) is None


@pytest.mark.parametrize("raw", [None, True, float("nan"), float("inf"), "now"])
def test_invalid_broker_tick_timestamp_never_looks_fresh(raw):
    now = datetime.now(timezone.utc)
    config = replace(CONFIG, server_utc_offset_seconds=10800)
    assert fresh_demo_quote_age_ms(SimpleNamespace(time_msc=raw), config, now) is None


def test_oversized_broker_timestamp_fails_closed_without_integer_conversion():
    now = datetime.now(timezone.utc)
    config = replace(CONFIG, server_utc_offset_seconds=10800)
    assert fresh_demo_quote_age_ms(SimpleNamespace(time_msc=10 ** 10000), config, now) is None


@pytest.mark.parametrize("raw", ["010800", "+10800", " 10800", "3600", ""])
def test_offset_environment_requires_exact_operator_binding(monkeypatch, raw):
    monkeypatch.setenv("SHREEK_DEMO_SERVER_UTC_OFFSET_SECONDS", raw)
    with pytest.raises(ValueError):
        configured_demo_server_utc_offset_seconds()
