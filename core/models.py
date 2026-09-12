"""
Typed data models replacing ad-hoc dictionaries used by the V5.1 engine.
These models are deliberately stable because market, risk, execution and
journal layers exchange them directly.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from core.enums import Direction, StructureEvent, SetupType, SignalStatus, Timeframe, TradeState

@dataclass(frozen=True)
class MarketStructure:
    timeframe: Timeframe
    bias: Direction
    event: StructureEvent
    last_swing_high: Optional[float]
    last_swing_low: Optional[float]
    is_ranging: bool = False
    @property
    def has_valid_swings(self) -> bool:
        return self.last_swing_high is not None and self.last_swing_low is not None

@dataclass(frozen=True)
class OrderBlock:
    high: float
    low: float
    bar_index: int
    body_size: float
    direction: Direction
    dist_to_price: Optional[float] = None
    proximity_to_swing: Optional[float] = None
    @property
    def mid(self) -> float: return (self.high + self.low) / 2.0

@dataclass(frozen=True)
class FairValueGap:
    kind: str
    top: float
    bottom: float
    formed_at: int
    @property
    def midpoint(self) -> float: return (self.top + self.bottom) / 2.0
    def overlaps(self, ob: OrderBlock) -> bool:
        return not (self.top < ob.low or self.bottom > ob.high)

@dataclass(frozen=True)
class LiquiditySweep:
    swept_high: bool
    swept_low: bool
    details: str = ""

@dataclass(frozen=True)
class PDArrayZone:
    zone_top: Optional[float]
    zone_bottom: Optional[float]
    equilibrium: Optional[float]
    order_block: Optional[OrderBlock] = None
    fvg: Optional[FairValueGap] = None
    swing_high: Optional[float] = None
    swing_low: Optional[float] = None
    @property
    def is_valid(self) -> bool:
        return self.zone_top is not None and self.zone_bottom is not None

@dataclass
class TradeSignal:
    status: SignalStatus
    setup_type: SetupType
    frame: Timeframe
    direction: Direction
    entry_price: float
    sl_price: float = 0.0
    confidence: float = 0.0
    details: str = ""
    candle_confirmation: bool = False
    bos_confirmed: bool = False
    sweep_confirmed: bool = False
    fvg_failure: bool = False
    aligned: bool = True
    order_block: Optional[OrderBlock] = None
    fvg: Optional[FairValueGap] = None
    structure: Optional[MarketStructure] = None
    @property
    def is_valid(self) -> bool: return self.status == SignalStatus.VALID

@dataclass
class ExecutionLevels:
    entry: float
    sl: float
    tp1: float
    tp2: float
    tp3: float
    risk: float
    rr1: float
    setup_type: SetupType
    confidence: float
    selected_frame: Timeframe
    details: str = ""

@dataclass
class Position:
    symbol: str
    direction: Direction
    state: TradeState
    entry: float
    sl: float
    tp1: float
    tp2: float
    tp3: float
    score: int
    setup_type: SetupType
    volume: float = 0.0
    opened_at: Optional[datetime] = None
    ticket: Optional[int] = None
    partial_closed_tp1: bool = False
    partial_closed_tp2: bool = False
    moved_to_breakeven: bool = False
    trailing_active: bool = False

@dataclass
class TradeResult:
    timestamp: datetime
    symbol: str
    direction: Direction
    score: int
    entry: float
    sl: float
    tp1: float
    tp2: float
    tp3: float
    result: str = "OPEN"
    exit_price: Optional[float] = None
    exit_reason: str = ""
    pnl: Optional[float] = None
    m15_setup: str = ""

@dataclass
class ConfluenceCriterion:
    name: str
    points: int
    max_points: int
    reason: str

@dataclass
class ConfluenceResult:
    score: int
    criteria: list[ConfluenceCriterion] = field(default_factory=list)
    direction: Direction = Direction.UNKNOWN
    @property
    def max_score(self) -> int: return sum(c.max_points for c in self.criteria)
    @property
    def score_ratio(self) -> float:
        m = self.max_score
        return round(self.score / m, 3) if m else 0.0
