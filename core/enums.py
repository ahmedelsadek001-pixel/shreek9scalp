"""Enumerations shared across the engine. Replaces v4 raw strings with typed values."""
from __future__ import annotations
from enum import Enum

class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    RANGE = "RANGE"
    UNKNOWN = "UNKNOWN"

class StructureEvent(str, Enum):
    BOS_BULLISH = "BOS_BULLISH"
    BOS_BEARISH = "BOS_BEARISH"
    CHOCH_BULLISH = "CHoCH_BULLISH"
    CHOCH_BEARISH = "CHoCH_BEARISH"
    NONE = "NONE"

class SetupType(str, Enum):
    NONE = "NONE"
    COMBINED = "COMBINED"
    OB_ENTRY = "OB_ENTRY"
    FVG_ENTRY = "FVG_ENTRY"
    SWEEP_ENTRY = "SWEEP_ENTRY"
    FVG_FAILURE = "FVG_FAILURE"

class SignalStatus(str, Enum):
    WAIT = "WAIT"
    NO_SIGNAL = "NO_SIGNAL"
    VALID = "VALID"

class Timeframe(str, Enum):
    D1 = "D1"
    H4 = "H4"
    H1 = "H1"
    M15 = "M15"
    M5 = "M5"
    M3 = "M3"

class TradeState(str, Enum):
    WAITING = "WAITING"
    SIGNAL = "SIGNAL"
    CONFIRMED = "CONFIRMED"
    OPEN = "OPEN"
    MANAGING = "MANAGING"
    PARTIAL_CLOSE = "PARTIAL_CLOSE"
    BREAK_EVEN = "BREAK_EVEN"
    TRAILING = "TRAILING"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"
