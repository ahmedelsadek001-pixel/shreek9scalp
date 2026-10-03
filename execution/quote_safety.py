"""Fail-closed quote freshness and execution deviation gate for SHREEK V5.3."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import isfinite
from core.enums import Direction
from execution.decision_provenance import IssuedDecisionRegistry

_QUOTE_DECISION_CAPABILITY = object()
_ISSUED_QUOTES = IssuedDecisionRegistry()


def _utc_snapshot(value: object) -> datetime | None:
    """Copy an aware timestamp without retaining caller-owned timezone state."""
    if not isinstance(value, datetime) or value.tzinfo is None:
        return None
    try:
        offset = value.utcoffset()
        if offset is None:
            return None
        # Build a base datetime so a datetime subclass cannot retain custom
        # behaviour in issued evidence. Use the captured offset exactly once;
        # a mutable tzinfo cannot change the stored instant after issuance.
        wall_time = datetime(
            value.year, value.month, value.day,
            value.hour, value.minute, value.second, value.microsecond,
            fold=value.fold,
        )
        return (wall_time - offset).replace(tzinfo=timezone.utc)
    except Exception:
        # Timezone providers are external inputs and may raise arbitrary
        # exceptions. Invalid timing evidence must reject rather than escape.
        return None


@dataclass(frozen=True)
class QuoteSafetyDecision:
    allowed: bool
    reason: str
    intended_price: float | None = None
    _capability: object | None = field(default=None, repr=False, compare=False)
    quote_time: datetime | None = None
    evaluated_at: datetime | None = None
    max_age_seconds: float | None = None
    symbol: str | None = None
    direction: Direction | None = None


def is_quote_issued(decision: QuoteSafetyDecision) -> bool:
    """Reject caller-created approval flags at the transport boundary."""
    return (
        isinstance(decision, QuoteSafetyDecision)
        and decision._capability is _QUOTE_DECISION_CAPABILITY
        and _ISSUED_QUOTES.is_issued(
            decision, (
                decision.allowed, decision.reason, decision.intended_price,
                decision.quote_time, decision.evaluated_at, decision.max_age_seconds,
                decision.symbol, decision.direction,
            ),
        )
    )

def evaluate_quote_safety(*, symbol:str, direction:Direction, quote_time:datetime, now:datetime, intended_price:float, market_price:float, max_age_seconds:float, max_deviation_points:float, point_size:float)->QuoteSafetyDecision:
    if not isinstance(symbol,str) or not symbol.strip() or symbol != symbol.strip():
        return QuoteSafetyDecision(False,"quote symbol must be exact and non-empty")
    if type(direction) is not Direction or direction not in (Direction.BUY,Direction.SELL):
        return QuoteSafetyDecision(False,"quote direction must be BUY or SELL")
    quote_utc = _utc_snapshot(quote_time)
    now_utc = _utc_snapshot(now)
    if quote_utc is None or now_utc is None:
        return QuoteSafetyDecision(False,"timestamps must be timezone-aware")
    values=(intended_price,market_price,max_age_seconds,max_deviation_points,point_size)
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) for v in values):
        return QuoteSafetyDecision(False,"quote safety inputs must be numeric")
    vals=tuple(float(v) for v in values)
    if not all(isfinite(v) for v in vals):
        return QuoteSafetyDecision(False,"quote safety inputs must be finite")
    intended,market,max_age,max_dev,point=vals
    if intended<=0 or market<=0 or max_age<0 or max_dev<0 or point<=0:
        return QuoteSafetyDecision(False,"quote safety inputs outside valid range")
    age=(now_utc-quote_utc).total_seconds()
    if age<0:
        return QuoteSafetyDecision(False,"quote timestamp is in the future")
    if age>max_age:
        return QuoteSafetyDecision(False,"quote is stale")
    deviation=abs(market-intended)/point
    if deviation>max_dev:
        return QuoteSafetyDecision(False,"market price deviation exceeds limit")
    decision = QuoteSafetyDecision(
        True,"quote freshness and deviation accepted",intended,
        _QUOTE_DECISION_CAPABILITY,quote_utc,now_utc,max_age,symbol,direction,
    )
    _ISSUED_QUOTES.issue(decision, (
        decision.allowed, decision.reason, decision.intended_price,
        decision.quote_time, decision.evaluated_at, decision.max_age_seconds,
        decision.symbol, decision.direction,
    ))
    return decision
