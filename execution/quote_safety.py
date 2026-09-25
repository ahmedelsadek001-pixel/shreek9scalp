"""Fail-closed quote freshness and execution deviation gate for SHREEK V5.3."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from math import isfinite
from execution.decision_provenance import IssuedDecisionRegistry

_QUOTE_DECISION_CAPABILITY = object()
_ISSUED_QUOTES = IssuedDecisionRegistry()

@dataclass(frozen=True)
class QuoteSafetyDecision:
    allowed: bool
    reason: str
    intended_price: float | None = None
    _capability: object | None = field(default=None, repr=False, compare=False)
    quote_time: datetime | None = None
    evaluated_at: datetime | None = None
    max_age_seconds: float | None = None


def is_quote_issued(decision: QuoteSafetyDecision) -> bool:
    """Reject caller-created approval flags at the transport boundary."""
    return (
        isinstance(decision, QuoteSafetyDecision)
        and decision._capability is _QUOTE_DECISION_CAPABILITY
        and _ISSUED_QUOTES.is_issued(
            decision, (
                decision.allowed, decision.reason, decision.intended_price,
                decision.quote_time, decision.evaluated_at, decision.max_age_seconds,
            ),
        )
    )

def evaluate_quote_safety(*, quote_time:datetime, now:datetime, intended_price:float, market_price:float, max_age_seconds:float, max_deviation_points:float, point_size:float)->QuoteSafetyDecision:
    if not isinstance(quote_time,datetime) or not isinstance(now,datetime) or quote_time.tzinfo is None or now.tzinfo is None:
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
    age=(now-quote_time).total_seconds()
    if age<0:
        return QuoteSafetyDecision(False,"quote timestamp is in the future")
    if age>max_age:
        return QuoteSafetyDecision(False,"quote is stale")
    deviation=abs(market-intended)/point
    if deviation>max_dev:
        return QuoteSafetyDecision(False,"market price deviation exceeds limit")
    decision = QuoteSafetyDecision(
        True,"quote freshness and deviation accepted",intended,
        _QUOTE_DECISION_CAPABILITY,quote_time,now,max_age,
    )
    _ISSUED_QUOTES.issue(decision, (
        decision.allowed, decision.reason, decision.intended_price,
        decision.quote_time, decision.evaluated_at, decision.max_age_seconds,
    ))
    return decision
