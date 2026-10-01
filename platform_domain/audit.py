"""Deterministic append-oriented audit event contract for SHREEK."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import json

AUDIT_SCHEMA_VERSION = "1"

@dataclass(frozen=True)
class AuditEvent:
    schema_version: str
    event_id: str
    event_type: str
    subject_id: str
    occurred_at: datetime
    object_id: str
    payload_fingerprint: str
    previous_event_fingerprint: str | None = None

    def validate(self) -> None:
        if self.schema_version != AUDIT_SCHEMA_VERSION:
            raise ValueError("unsupported audit schema version")
        for name in ("event_id", "event_type", "subject_id", "object_id"):
            if type(getattr(self, name)) is not str or not getattr(self, name).strip():
                raise ValueError(f"{name} must be non-empty text")
        if not isinstance(self.occurred_at, datetime) or self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")
        for name in ("payload_fingerprint",):
            value=getattr(self,name)
            if len(value)!=64 or any(c not in "0123456789abcdef" for c in value):
                raise ValueError(f"{name} must be lowercase SHA-256")
        if self.previous_event_fingerprint is not None:
            value=self.previous_event_fingerprint
            if type(value) is not str or len(value)!=64 or any(c not in "0123456789abcdef" for c in value):
                raise ValueError("previous_event_fingerprint must be lowercase SHA-256")

def serialize_audit_event(event: AuditEvent) -> str:
    if not isinstance(event, AuditEvent):
        raise ValueError("event must be AuditEvent")
    event.validate()
    return json.dumps(asdict(event), sort_keys=True, separators=(",", ":"), default=str)

def fingerprint_audit_event(event: AuditEvent) -> str:
    return sha256(serialize_audit_event(event).encode("utf-8")).hexdigest()

def verify_audit_chain(events: tuple[AuditEvent, ...]) -> bool:
    if type(events) is not tuple:
        return False
    previous=None
    for event in events:
        try:
            event.validate()
        except (TypeError, ValueError, OverflowError):
            return False
        if event.previous_event_fingerprint != previous:
            return False
        previous=fingerprint_audit_event(event)
    return True
