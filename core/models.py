from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from core.enums import Direction

@dataclass(frozen=True)
class FairValueGap:
    kind: str
    top: float
    bottom: float
    formed_at: int
    @property
    def midpoint(self) -> float: return (self.top+self.bottom)/2
    def overlaps(self, other) -> bool: return max(self.bottom, other.bottom) <= min(self.top, other.top)

@dataclass(frozen=True)
class OrderBlock:
    kind: str
    top: float
    bottom: float
    formed_at: int
    @property
    def midpoint(self) -> float: return (self.top+self.bottom)/2

@dataclass(frozen=True)
class LiquiditySweep:
    swept_high: bool
    swept_low: bool
    details: str = ""

@dataclass(frozen=True)
class MarketStructure:
    trend: Optional[Direction] = None
    last_swing_high: Optional[float] = None
    last_swing_low: Optional[float] = None
    bos: bool = False
    choch: bool = False
    mss: bool = False
    details: str = ""

@dataclass(frozen=True)
class Signal:
    symbol: str
    direction: Direction
    score: float
    entry: float
    stop_loss: float
    take_profit: float
    timestamp: datetime
    reasons: tuple[str,...] = ()
    signal_id: str = ""
