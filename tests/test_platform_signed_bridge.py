from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from platform_domain.bridge_protocol import BridgeMode, BridgeRequest
from platform_domain.signed_bridge import sign_bridge_request, verify_bridge_envelope

NOW = datetime(2026, 9, 22, 11, 30, tzinfo=timezone.utc)
KEY = b"k" * 32
OTHER_KEY = b"x" * 32

def _request():
    return BridgeRequest(
        "req-1", "acct-1", "a" * 64, NOW,
        NOW + timedelta(minutes=1), BridgeMode.PAPER,
    )

def test_signed_bridge_envelope_verifies_with_correct_key():
    envelope = sign_bridge_request(_request(), key=KEY)
    assert verify_bridge_envelope(envelope, key=KEY)
    assert not verify_bridge_envelope(envelope, key=OTHER_KEY)

def test_tampering_request_after_signing_is_detected():
    envelope = sign_bridge_request(_request(), key=KEY)
    tampered = replace(
        envelope,
        request=replace(envelope.request, account_binding="acct-2"),
    )
    assert not verify_bridge_envelope(tampered, key=KEY)

def test_tampering_signature_is_detected():
    envelope = sign_bridge_request(_request(), key=KEY)
    assert not verify_bridge_envelope(
        replace(envelope, signature="0" * 64), key=KEY
    )

@pytest.mark.parametrize("key", [b"", b"x" * 16, "not-bytes"])
def test_weak_or_wrong_type_signing_key_is_rejected(key):
    with pytest.raises(ValueError):
        sign_bridge_request(_request(), key=key)

def test_signed_transport_still_has_no_live_mode():
    assert "live" not in {mode.value for mode in BridgeMode}
