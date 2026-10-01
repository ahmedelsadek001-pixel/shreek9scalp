"""Authenticated-envelope primitives for the future local SHREEK bridge.

This module validates requests only. It contains no MT5 order execution.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class BridgeMode(str, Enum):
    OBSERVE = "observe"
    PAPER = "paper"
    DEMO = "demo"

@dataclass(frozen=True)
class BridgeRequest:
    request_id: str
    account_binding: str
    signal_fingerprint: str
    issued_at: datetime
    expires_at: datetime
    mode: BridgeMode

    def validate(self) -> None:
        for name in ("request_id","account_binding"):
            if type(getattr(self,name)) is not str or not getattr(self,name).strip():
                raise ValueError(f"{name} must be non-empty text")
        if type(self.signal_fingerprint) is not str or len(self.signal_fingerprint)!=64 or any(c not in "0123456789abcdef" for c in self.signal_fingerprint):
            raise ValueError("signal_fingerprint must be lowercase SHA-256")
        for value in (self.issued_at,self.expires_at):
            if not isinstance(value,datetime) or value.tzinfo is None:
                raise ValueError("bridge timestamps must be timezone-aware")
        if self.issued_at >= self.expires_at:
            raise ValueError("bridge request expiry must be after issue")
        if not isinstance(self.mode,BridgeMode):
            raise ValueError("mode must be BridgeMode")

    def is_acceptable(self, *, at: datetime, expected_account: str) -> bool:
        try: self.validate()
        except (TypeError,ValueError,OverflowError): return False
        return isinstance(at,datetime) and at.tzinfo is not None and self.issued_at <= at < self.expires_at and expected_account == self.account_binding
