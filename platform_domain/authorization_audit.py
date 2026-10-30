"""Audit projection for commercial authorization decisions."""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256

from platform_domain.audit import AuditEvent
from platform_domain.authorization import CommercialAuthorization


def authorization_audit_event(
    authorization: CommercialAuthorization,
    *,
    event_id: str,
    subject_id: str,
    request_id: str,
    occurred_at: datetime,
    previous_event_fingerprint: str | None = None,
) -> AuditEvent:
    authorization.validate()
    if type(request_id) is not str or not request_id.strip():
        raise ValueError("request_id must be non-empty text")

    payload = (
        f"{authorization.allowed}|{authorization.reason.value}|"
        f"{authorization.signal_fingerprint or ''}"
    )
    payload_fingerprint = sha256(payload.encode("utf-8")).hexdigest()
    event = AuditEvent(
        schema_version="1",
        event_id=event_id,
        event_type=(
            "commercial.authorization.allowed"
            if authorization.allowed
            else "commercial.authorization.denied"
        ),
        subject_id=subject_id,
        occurred_at=occurred_at,
        object_id=request_id,
        payload_fingerprint=payload_fingerprint,
        previous_event_fingerprint=previous_event_fingerprint,
    )
    event.validate()
    return event
