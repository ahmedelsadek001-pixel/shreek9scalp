"""In-memory protocol-level replay protection for commercial bridge requests.

This is independent of broker execution idempotency and never authorizes live trading.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

class RequestState(str, Enum):
    NEW = "new"
    IN_FLIGHT = "in_flight"
    ACCEPTED = "accepted"
    REJECTED = "rejected"

@dataclass(frozen=True)
class RequestIdentity:
    request_id: str
    signal_fingerprint: str
    account_binding: str

    def validate(self) -> None:
        for name in ("request_id", "account_binding"):
            value = getattr(self, name)
            if type(value) is not str or not value.strip():
                raise ValueError(f"{name} must be non-empty text")
        value = self.signal_fingerprint
        if type(value) is not str or len(value) != 64 or any(
            char not in "0123456789abcdef" for char in value
        ):
            raise ValueError("signal_fingerprint must be lowercase SHA-256")

class CommercialReplayGuard:
    def __init__(self) -> None:
        self._states: dict[RequestIdentity, RequestState] = {}

    def state(self, identity: RequestIdentity) -> RequestState:
        try:
            identity.validate()
        except (TypeError, ValueError, OverflowError):
            return RequestState.REJECTED
        return self._states.get(identity, RequestState.NEW)

    def begin(self, identity: RequestIdentity) -> bool:
        if self.state(identity) is not RequestState.NEW:
            return False
        self._states[identity] = RequestState.IN_FLIGHT
        return True

    def finish(self, identity: RequestIdentity, *, accepted: bool) -> bool:
        if type(accepted) is not bool or self.state(identity) is not RequestState.IN_FLIGHT:
            return False
        self._states[identity] = (
            RequestState.ACCEPTED if accepted else RequestState.REJECTED
        )
        return True
