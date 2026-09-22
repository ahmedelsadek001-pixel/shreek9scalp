from datetime import datetime, timedelta, timezone

from platform_domain.authorization import AuthorizationReason
from platform_domain.bridge_protocol import BridgeMode, BridgeRequest
from platform_domain.commercial_idempotency import (
    CommercialReplayGuard,
    RequestIdentity,
    RequestState,
)
from platform_domain.commercial_service import evaluate_bridge_request
from platform_domain.entitlements import Capability, Entitlement
from platform_domain.signals import SignalEnvelope, fingerprint_signal

NOW = datetime(2026, 9, 22, 11, 0, tzinfo=timezone.utc)

def _objects():
    signal = SignalEnvelope(
        "1", "sig-1", "strategy-1", "5.2", "XAUUSD", "BUY",
        NOW - timedelta(minutes=1), NOW + timedelta(minutes=10),
        "a" * 64, 4300.0, 4290.0, 4320.0,
    )
    entitlement = Entitlement(
        "customer-1", frozenset({Capability.SIGNALS, Capability.BRIDGE}),
        NOW - timedelta(days=1), NOW + timedelta(days=30),
    )
    request = BridgeRequest(
        "req-1", "acct-1", fingerprint_signal(signal),
        NOW - timedelta(seconds=1), NOW + timedelta(minutes=1), BridgeMode.PAPER,
    )
    return signal, entitlement, request

def test_service_accepts_once_then_blocks_replay():
    signal, entitlement, request = _objects()
    guard = CommercialReplayGuard()
    first = evaluate_bridge_request(
        guard=guard, entitlement=entitlement, signal=signal, request=request,
        subject_id="customer-1", expected_account="acct-1", at=NOW,
    )
    second = evaluate_bridge_request(
        guard=guard, entitlement=entitlement, signal=signal, request=request,
        subject_id="customer-1", expected_account="acct-1", at=NOW,
    )
    assert first.authorization.allowed
    assert not first.replay_blocked
    assert not second.authorization.allowed
    assert second.replay_blocked

def test_rejected_request_cannot_be_replayed():
    signal, entitlement, request = _objects()
    guard = CommercialReplayGuard()
    first = evaluate_bridge_request(
        guard=guard, entitlement=entitlement, signal=signal, request=request,
        subject_id="customer-1", expected_account="wrong", at=NOW,
    )
    second = evaluate_bridge_request(
        guard=guard, entitlement=entitlement, signal=signal, request=request,
        subject_id="customer-1", expected_account="acct-1", at=NOW,
    )
    assert first.authorization.reason is AuthorizationReason.BRIDGE_REQUEST_DENIED
    assert second.replay_blocked

def test_guard_rejects_invalid_identity_and_invalid_finish_transition():
    guard = CommercialReplayGuard()
    bad = RequestIdentity("req-1", "bad", "acct-1")
    assert guard.state(bad) is RequestState.REJECTED
    assert not guard.begin(bad)
    signal, _, request = _objects()
    identity = RequestIdentity(request.request_id, fingerprint_signal(signal), "acct-1")
    assert not guard.finish(identity, accepted=True)
