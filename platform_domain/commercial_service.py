"""Application service boundary for non-live commercial bridge access."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime

from platform_domain.authorization import (
    AuthorizationReason,
    CommercialAuthorization,
    authorize_bridge_access,
)
from platform_domain.bridge_protocol import BridgeRequest
from platform_domain.commercial_idempotency import CommercialReplayGuard, RequestIdentity
from platform_domain.entitlements import Entitlement
from platform_domain.signals import SignalEnvelope

@dataclass(frozen=True)
class BridgeAccessDecision:
    authorization: CommercialAuthorization
    replay_blocked: bool

def evaluate_bridge_request(
    *,
    guard: CommercialReplayGuard,
    entitlement: Entitlement,
    signal: SignalEnvelope,
    request: BridgeRequest,
    subject_id: str,
    expected_account: str,
    at: datetime,
) -> BridgeAccessDecision:
    if not isinstance(guard, CommercialReplayGuard) or not isinstance(request, BridgeRequest):
        return BridgeAccessDecision(
            CommercialAuthorization(False, AuthorizationReason.INVALID_CONTEXT),
            False,
        )
    identity = RequestIdentity(
        request.request_id,
        request.signal_fingerprint,
        request.account_binding,
    )
    if not guard.begin(identity):
        return BridgeAccessDecision(
            CommercialAuthorization(False, AuthorizationReason.INVALID_CONTEXT),
            True,
        )
    authorization = authorize_bridge_access(
        entitlement=entitlement,
        signal=signal,
        request=request,
        subject_id=subject_id,
        expected_account=expected_account,
        at=at,
    )
    guard.finish(identity, accepted=authorization.allowed)
    return BridgeAccessDecision(authorization, False)
