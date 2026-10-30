from datetime import datetime, timedelta, timezone

import pytest

from platform_domain.entitlements import Capability, Entitlement, is_entitled


NOW = datetime(2026, 9, 22, tzinfo=timezone.utc)


def _entitlement(**changes):
    values = {
        "subject_id": "customer-1",
        "capabilities": frozenset({Capability.SIGNALS, Capability.RESEARCH_EVIDENCE}),
        "starts_at": NOW - timedelta(days=1),
        "expires_at": NOW + timedelta(days=30),
        "revoked": False,
    }
    values.update(changes)
    return Entitlement(**values)


def test_active_entitlement_grants_only_declared_capability():
    item = _entitlement()
    assert is_entitled(item, Capability.SIGNALS, at=NOW)
    assert not is_entitled(item, Capability.BRIDGE, at=NOW)


def test_expired_future_and_revoked_entitlements_fail_closed():
    assert not is_entitled(_entitlement(expires_at=NOW), Capability.SIGNALS, at=NOW)
    assert not is_entitled(_entitlement(starts_at=NOW + timedelta(seconds=1)), Capability.SIGNALS, at=NOW)
    assert not is_entitled(_entitlement(revoked=True), Capability.SIGNALS, at=NOW)


@pytest.mark.parametrize("at", [None, NOW.replace(tzinfo=None), "2026-09-22"])
def test_invalid_authorization_time_fails_closed(at):
    assert not is_entitled(_entitlement(), Capability.SIGNALS, at=at)


def test_malformed_entitlement_fails_closed_in_authorizer():
    malformed = _entitlement(capabilities=frozenset({"signals"}))
    assert not is_entitled(malformed, Capability.SIGNALS, at=NOW)


def test_entitlement_has_no_live_execution_capability():
    assert "live_execution" not in {item.value for item in Capability}
