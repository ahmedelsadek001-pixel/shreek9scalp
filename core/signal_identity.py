"""Deterministic identity for closed-candle signals.

The identity intentionally excludes mutable values such as current price and
score. A signal belongs to the closed candle/setup event that generated it.
"""
from __future__ import annotations
import hashlib

def signal_fingerprint(symbol: str, candle_time: str, direction: str,
                       setup_type: str, frame: str) -> str:
    payload = "|".join((symbol.upper(), candle_time, direction.upper(), setup_type.upper(), frame.upper()))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
