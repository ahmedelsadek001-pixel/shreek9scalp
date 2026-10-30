"""Thread-safe deterministic duplicate-signal guard for SHREEK V5.1.

The guard provides stable signal identity and atomic idempotent reservation.
It has no execution authority and stores only in-memory identities.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from threading import Lock

from core.enums import Direction, SetupType, Timeframe
from core.models import TradeSignal


@dataclass(frozen=True)
class DuplicateDecision:
    allowed: bool
    fingerprint: str
    reason: str


def signal_fingerprint(symbol: str, signal: TradeSignal) -> str:
    """Return a stable identity for the executable characteristics of a signal."""
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("symbol is required")
    if not isinstance(signal, TradeSignal):
        raise TypeError("signal must be TradeSignal")
    if not isinstance(signal.setup_type, SetupType):
        raise ValueError("signal setup_type is invalid")
    if not isinstance(signal.frame, Timeframe):
        raise ValueError("signal frame is invalid")
    if not isinstance(signal.direction, Direction):
        raise ValueError("signal direction is invalid")
    try:
        prices = (float(signal.entry_price), float(signal.sl_price))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("signal prices must be finite") from exc
    if not all(isfinite(value) for value in prices):
        raise ValueError("signal prices must be finite")
    values = (
        symbol.strip().upper(),
        signal.setup_type.value,
        signal.frame.value,
        signal.direction.value,
        repr(prices[0]),
        repr(prices[1]),
    )
    return sha256("|".join(values).encode("utf-8")).hexdigest()


class DuplicateSignalGuard:
    """Atomic process-local idempotency boundary that fails closed on duplicates."""

    def __init__(self) -> None:
        self._seen: set[str] = set()
        self._lock = Lock()

    def check(self, fingerprint: str) -> DuplicateDecision:
        if not isinstance(fingerprint, str) or not fingerprint:
            raise ValueError("fingerprint is required")
        with self._lock:
            if fingerprint in self._seen:
                return DuplicateDecision(False, fingerprint, "duplicate signal identity")
            return DuplicateDecision(True, fingerprint, "signal identity is new")

    def reserve(self, fingerprint: str) -> DuplicateDecision:
        if not isinstance(fingerprint, str) or not fingerprint:
            raise ValueError("fingerprint is required")
        with self._lock:
            if fingerprint in self._seen:
                return DuplicateDecision(False, fingerprint, "duplicate signal identity")
            self._seen.add(fingerprint)
            return DuplicateDecision(True, fingerprint, "signal identity reserved")

    def discard(self, fingerprint: str) -> None:
        if not isinstance(fingerprint, str) or not fingerprint:
            raise ValueError("fingerprint is required")
        with self._lock:
            self._seen.discard(fingerprint)

    def contains(self, fingerprint: str) -> bool:
        if not isinstance(fingerprint, str) or not fingerprint:
            raise ValueError("fingerprint is required")
        with self._lock:
            return fingerprint in self._seen

    def size(self) -> int:
        with self._lock:
            return len(self._seen)
