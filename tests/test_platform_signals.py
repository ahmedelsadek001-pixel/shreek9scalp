from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from platform_domain.signals import SignalEnvelope, fingerprint_signal, serialize_signal


NOW = datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc)


def _signal(**changes):
    values = {
        "schema_version": "1",
        "signal_id": "sig-001",
        "strategy_id": "shreek-breakout-retest",
        "strategy_version": "5.2",
        "symbol": "XAUUSD",
        "side": "BUY",
        "created_at": NOW,
        "expires_at": NOW + timedelta(minutes=15),
        "evidence_fingerprint": "a" * 64,
        "entry": 4300.0,
        "stop_loss": 4290.0,
        "take_profit": 4320.0,
    }
    values.update(changes)
    return SignalEnvelope(**values)


def test_signal_is_deterministic_and_evidence_bound():
    signal = _signal()
    assert serialize_signal(signal) == serialize_signal(signal)
    assert fingerprint_signal(signal) == fingerprint_signal(signal)
    changed = replace(signal, evidence_fingerprint="b" * 64)
    assert fingerprint_signal(changed) != fingerprint_signal(signal)


def test_signal_activity_has_strict_expiry():
    signal = _signal()
    assert signal.is_active(at=NOW)
    assert not signal.is_active(at=signal.expires_at)


@pytest.mark.parametrize(
    "changes",
    [
        {"side": "HOLD"},
        {"created_at": NOW.replace(tzinfo=None)},
        {"expires_at": NOW},
        {"evidence_fingerprint": "bad"},
        {"entry": float("nan")},
        {"stop_loss": 4310.0},
        {"take_profit": 4290.0},
    ],
)
def test_malformed_buy_signal_fails_closed(changes):
    signal = _signal(**changes)
    with pytest.raises(ValueError):
        signal.validate()
    assert not signal.is_active(at=NOW)


def test_sell_signal_enforces_inverse_price_geometry():
    signal = _signal(side="SELL", stop_loss=4310.0, take_profit=4280.0)
    signal.validate()
    invalid = replace(signal, stop_loss=4290.0)
    with pytest.raises(ValueError, match="SELL price geometry"):
        invalid.validate()
