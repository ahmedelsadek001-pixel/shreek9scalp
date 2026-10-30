"""Fail-closed commercial capability and entitlement domain model.

Entitlements grant product access only. They never authorize broker execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class Capability(str, Enum):
    SIGNALS = "signals"
    ADVANCED_ANALYTICS = "advanced_analytics"
    RESEARCH_EVIDENCE = "research_evidence"
    RISK_TOOLS = "risk_tools"
    BRIDGE = "bridge"


@dataclass(frozen=True)
class Entitlement:
    subject_id: str
    capabilities: frozenset[Capability]
    starts_at: datetime
    expires_at: datetime
    revoked: bool = False

    def validate(self) -> None:
        if type(self.subject_id) is not str or not self.subject_id.strip():
            raise ValueError("subject_id must be non-empty text")
        if type(self.capabilities) is not frozenset or any(
            not isinstance(item, Capability) for item in self.capabilities
        ):
            raise ValueError("capabilities must be a frozenset of Capability values")
        for value in (self.starts_at, self.expires_at):
            if not isinstance(value, datetime) or value.tzinfo is None:
                raise ValueError("entitlement timestamps must be timezone-aware")
        if self.starts_at >= self.expires_at:
            raise ValueError("entitlement expiry must be after start")
        if type(self.revoked) is not bool:
            raise ValueError("revoked must be bool")


def is_entitled(
    entitlement: Entitlement,
    capability: Capability,
    *,
    at: datetime,
) -> bool:
    """Return product-access authorization, failing closed on malformed input."""
    if not isinstance(entitlement, Entitlement):
        return False
    try:
        entitlement.validate()
    except (TypeError, ValueError, OverflowError):
        return False
    if not isinstance(capability, Capability):
        return False
    if not isinstance(at, datetime) or at.tzinfo is None:
        return False
    if entitlement.revoked:
        return False
    return entitlement.starts_at <= at < entitlement.expires_at and capability in entitlement.capabilities
