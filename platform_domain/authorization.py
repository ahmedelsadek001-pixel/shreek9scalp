"""Fail-closed commercial authorization pipeline.

This authorizes non-live product/bridge access only. It cannot authorize live trading.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from platform_domain.bridge_protocol import BridgeRequest
from platform_domain.entitlements import Capability, Entitlement, is_entitled
from platform_domain.signals import SignalEnvelope, fingerprint_signal


class AuthorizationReason(str, Enum):
    ALLOWED = "allowed"
    INVALID_CONTEXT = "invalid_context"
    SUBJECT_MISMATCH = "subject_mismatch"
    SIGNAL_INACTIVE = "signal_inactive"
    SIGNAL_FINGERPRINT_MISMATCH = "signal_fingerprint_mismatch"
    SIGNAL_ACCESS_DENIED = "signal_access_denied"
    BRIDGE_ACCESS_DENIED = "bridge_access_denied"
    BRIDGE_REQUEST_DENIED = "bridge_request_denied"


@dataclass(frozen=True)
class CommercialAuthorization:
    allowed: bool
    reason: AuthorizationReason
    signal_fingerprint: str | None = None

    def validate(self) -> None:
        if type(self.allowed) is not bool:
            raise ValueError("allowed must be bool")
        if not isinstance(self.reason, AuthorizationReason):
            raise ValueError("reason must be AuthorizationReason")
        if self.allowed != (self.reason is AuthorizationReason.ALLOWED):
            raise ValueError("authorization result is contradictory")
        if self.allowed:
            value = self.signal_fingerprint
            if type(value) is not str or len(value) != 64 or any(
                char not in "0123456789abcdef" for char in value
            ):
                raise ValueError("allowed authorization requires signal fingerprint")


def authorize_bridge_access(
    *,
    entitlement: Entitlement,
    signal: SignalEnvelope,
    request: BridgeRequest,
    subject_id: str,
    expected_account: str,
    at: datetime,
) -> CommercialAuthorization:
    """Authorize access to a non-live bridge request, failing closed."""
    if (
        type(subject_id) is not str
        or not subject_id.strip()
        or type(expected_account) is not str
        or not expected_account.strip()
        or not isinstance(at, datetime)
        or at.tzinfo is None
    ):
        return CommercialAuthorization(False, AuthorizationReason.INVALID_CONTEXT)

    if not isinstance(entitlement, Entitlement) or entitlement.subject_id != subject_id:
        return CommercialAuthorization(False, AuthorizationReason.SUBJECT_MISMATCH)

    if not isinstance(signal, SignalEnvelope) or not signal.is_active(at=at):
        return CommercialAuthorization(False, AuthorizationReason.SIGNAL_INACTIVE)

    try:
        signal_fingerprint = fingerprint_signal(signal)
    except (TypeError, ValueError, OverflowError):
        return CommercialAuthorization(False, AuthorizationReason.SIGNAL_INACTIVE)

    if not isinstance(request, BridgeRequest) or request.signal_fingerprint != signal_fingerprint:
        return CommercialAuthorization(
            False,
            AuthorizationReason.SIGNAL_FINGERPRINT_MISMATCH,
        )

    if not is_entitled(entitlement, Capability.SIGNALS, at=at):
        return CommercialAuthorization(False, AuthorizationReason.SIGNAL_ACCESS_DENIED)

    if not is_entitled(entitlement, Capability.BRIDGE, at=at):
        return CommercialAuthorization(False, AuthorizationReason.BRIDGE_ACCESS_DENIED)

    if not request.is_acceptable(at=at, expected_account=expected_account):
        return CommercialAuthorization(False, AuthorizationReason.BRIDGE_REQUEST_DENIED)

    result = CommercialAuthorization(
        True,
        AuthorizationReason.ALLOWED,
        signal_fingerprint,
    )
    result.validate()
    return result
