from dataclasses import replace
from datetime import datetime, timedelta, timezone

from platform_domain.authorization import AuthorizationReason, authorize_bridge_access
from platform_domain.bridge_protocol import BridgeMode, BridgeRequest
from platform_domain.entitlements import Capability, Entitlement
from platform_domain.signals import SignalEnvelope, fingerprint_signal


NOW = datetime(2026, 9, 22, 10, 30, tzinfo=timezone.utc)


def _signal():
    return SignalEnvelope(
        "1", "sig-1", "strategy-1", "5.2", "XAUUSD", "BUY",
        NOW - timedelta(minutes=1), NOW + timedelta(minutes=10),
        "a" * 64, 4300.0, 4290.0, 4320.0,
    )


def _entitlement():
    return Entitlement(
        "customer-1",
        frozenset({Capability.SIGNALS, Capability.BRIDGE}),
        NOW - timedelta(days=1),
        NOW + timedelta(days=30),
    )


def _request(signal):
    return BridgeRequest(
        "req-1", "acct-1", fingerprint_signal(signal),
        NOW - timedelta(seconds=5), NOW + timedelta(minutes=1),
        BridgeMode.PAPER,
    )


def _authorize(entitlement=None, signal=None, request=None, **changes):
    signal = signal or _signal()
    values = {
        "entitlement": entitlement or _entitlement(),
        "signal": signal,
        "request": request or _request(signal),
        "subject_id": "customer-1",
        "expected_account": "acct-1",
        "at": NOW,
    }
    values.update(changes)
    return authorize_bridge_access(**values)


def test_complete_commercial_chain_allows_non_live_bridge_access():
    result = _authorize()
    assert result.allowed
    assert result.reason is AuthorizationReason.ALLOWED
    result.validate()


def test_subject_mismatch_fails_closed():
    result = _authorize(subject_id="customer-2")
    assert not result.allowed
    assert result.reason is AuthorizationReason.SUBJECT_MISMATCH


def test_missing_bridge_entitlement_fails_closed():
    entitlement = replace(
        _entitlement(),
        capabilities=frozenset({Capability.SIGNALS}),
    )
    result = _authorize(entitlement=entitlement)
    assert result.reason is AuthorizationReason.BRIDGE_ACCESS_DENIED


def test_expired_signal_fails_closed():
    signal = replace(_signal(), expires_at=NOW)
    result = _authorize(signal=signal, request=_request(_signal()))
    assert result.reason is AuthorizationReason.SIGNAL_INACTIVE


def test_tampered_signal_breaks_request_binding():
    signal = _signal()
    request = _request(signal)
    tampered = replace(signal, take_profit=4330.0)
    result = _authorize(signal=tampered, request=request)
    assert result.reason is AuthorizationReason.SIGNAL_FINGERPRINT_MISMATCH


def test_wrong_account_fails_closed():
    result = _authorize(expected_account="acct-2")
    assert result.reason is AuthorizationReason.BRIDGE_REQUEST_DENIED


def test_revoked_entitlement_fails_closed():
    result = _authorize(entitlement=replace(_entitlement(), revoked=True))
    assert result.reason is AuthorizationReason.SIGNAL_ACCESS_DENIED


def test_commercial_pipeline_cannot_receive_live_mode():
    assert "live" not in {mode.value for mode in BridgeMode}
