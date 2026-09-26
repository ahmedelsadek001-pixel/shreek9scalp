from datetime import datetime, timezone

from platform_domain.audit import fingerprint_audit_event, verify_audit_chain
from platform_domain.authorization import AuthorizationReason, CommercialAuthorization
from platform_domain.authorization_audit import authorization_audit_event


NOW = datetime(2026, 9, 22, 10, 45, tzinfo=timezone.utc)


def test_authorization_decisions_project_into_verifiable_audit_chain():
    first = authorization_audit_event(
        CommercialAuthorization(False, AuthorizationReason.BRIDGE_ACCESS_DENIED),
        event_id="evt-1",
        subject_id="customer-1",
        request_id="req-1",
        occurred_at=NOW,
    )
    second = authorization_audit_event(
        CommercialAuthorization(True, AuthorizationReason.ALLOWED, "a" * 64),
        event_id="evt-2",
        subject_id="customer-1",
        request_id="req-2",
        occurred_at=NOW,
        previous_event_fingerprint=fingerprint_audit_event(first),
    )
    assert verify_audit_chain((first, second))
    assert first.event_type == "commercial.authorization.denied"
    assert second.event_type == "commercial.authorization.allowed"
