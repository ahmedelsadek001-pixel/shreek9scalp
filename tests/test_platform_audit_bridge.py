from dataclasses import replace
from datetime import datetime,timedelta,timezone
from platform_domain.audit import AuditEvent,fingerprint_audit_event,verify_audit_chain
from platform_domain.bridge_protocol import BridgeMode,BridgeRequest

NOW=datetime(2026,9,22,10,0,tzinfo=timezone.utc)

def _event(previous=None):
    return AuditEvent("1","evt-1","signal.published","system",NOW,"sig-1","a"*64,previous)

def test_audit_chain_detects_reordering_or_tampering():
    first=_event()
    second=replace(_event(fingerprint_audit_event(first)),event_id="evt-2")
    assert verify_audit_chain((first,second))
    assert not verify_audit_chain((second,first))
    assert not verify_audit_chain((first,replace(second,payload_fingerprint="b"*64)))

def test_bridge_has_no_live_mode_and_enforces_account_expiry():
    assert "live" not in {m.value for m in BridgeMode}
    req=BridgeRequest("req-1","acct-1","a"*64,NOW,NOW+timedelta(minutes=1),BridgeMode.PAPER)
    assert req.is_acceptable(at=NOW,expected_account="acct-1")
    assert not req.is_acceptable(at=req.expires_at,expected_account="acct-1")
    assert not req.is_acceptable(at=NOW,expected_account="acct-2")

def test_bridge_rejects_malformed_signal_identity():
    req=BridgeRequest("req-1","acct-1","bad",NOW,NOW+timedelta(minutes=1),BridgeMode.PAPER)
    assert not req.is_acceptable(at=NOW,expected_account="acct-1")
