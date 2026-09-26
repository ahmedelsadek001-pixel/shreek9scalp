"""Immutable, versioned signal contract for commercial SHREEK surfaces.

A signal is information. It is not an execution authorization.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import json
from math import isfinite
from typing import Any


SIGNAL_SCHEMA_VERSION = "1"


@dataclass(frozen=True)
class SignalEnvelope:
    schema_version: str
    signal_id: str
    strategy_id: str
    strategy_version: str
    symbol: str
    side: str
    created_at: datetime
    expires_at: datetime
    evidence_fingerprint: str
    entry: float
    stop_loss: float
    take_profit: float

    def validate(self) -> None:
        if self.schema_version != SIGNAL_SCHEMA_VERSION:
            raise ValueError("unsupported signal schema version")
        for name in ("signal_id", "strategy_id", "strategy_version", "symbol"):
            value = getattr(self, name)
            if type(value) is not str or not value.strip():
                raise ValueError(f"{name} must be non-empty text")
        if self.side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        for value in (self.created_at, self.expires_at):
            if not isinstance(value, datetime) or value.tzinfo is None:
                raise ValueError("signal timestamps must be timezone-aware")
        if self.created_at >= self.expires_at:
            raise ValueError("signal expiry must be after creation")
        if len(self.evidence_fingerprint) != 64 or any(
            c not in "0123456789abcdef" for c in self.evidence_fingerprint
        ):
            raise ValueError("evidence_fingerprint must be lowercase SHA-256")
        for name in ("entry", "stop_loss", "take_profit"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be positive and finite")
        if self.side == "BUY" and not (self.stop_loss < self.entry < self.take_profit):
            raise ValueError("BUY price geometry is invalid")
        if self.side == "SELL" and not (self.take_profit < self.entry < self.stop_loss):
            raise ValueError("SELL price geometry is invalid")

    def is_active(self, *, at: datetime) -> bool:
        try:
            self.validate()
        except (TypeError, ValueError, OverflowError):
            return False
        return isinstance(at, datetime) and at.tzinfo is not None and self.created_at <= at < self.expires_at


def serialize_signal(signal: SignalEnvelope) -> str:
    if not isinstance(signal, SignalEnvelope):
        raise ValueError("signal must be SignalEnvelope")
    signal.validate()
    payload: dict[str, Any] = asdict(signal)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint_signal(signal: SignalEnvelope) -> str:
    return sha256(serialize_signal(signal).encode("utf-8")).hexdigest()
