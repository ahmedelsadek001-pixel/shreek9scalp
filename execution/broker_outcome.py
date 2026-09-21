"""Explicit broker outcome classification for SHREEK V5.3.

Retry policy is deliberately conservative: ambiguous transport outcomes are
never retryable because the broker may already have accepted the order.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class BrokerOutcome(Enum):
    ACCEPTED="accepted"
    REJECTED_FINAL="rejected_final"
    REJECTED_RETRYABLE="rejected_retryable"
    UNKNOWN="unknown"


@dataclass(frozen=True)
class BrokerOutcomeDecision:
    outcome: BrokerOutcome
    retry_allowed: bool
    reason: str


def classify_broker_outcome(*, acknowledged: bool, accepted: bool | None, rejection_code: str | None = None) -> BrokerOutcomeDecision:
    if type(acknowledged) is not bool:
        raise ValueError("acknowledged must be bool")
    if accepted is not None and type(accepted) is not bool:
        raise ValueError("accepted must be bool or None")
    if rejection_code is not None and (not isinstance(rejection_code,str) or not rejection_code.strip()):
        raise ValueError("rejection_code must be a non-empty string or None")
    if not acknowledged or accepted is None:
        return BrokerOutcomeDecision(BrokerOutcome.UNKNOWN,False,"broker outcome ambiguous; reconciliation required")
    if accepted:
        if rejection_code is not None:
            raise ValueError("accepted outcome cannot include rejection_code")
        return BrokerOutcomeDecision(BrokerOutcome.ACCEPTED,False,"broker accepted order")
    if rejection_code is None:
        return BrokerOutcomeDecision(BrokerOutcome.REJECTED_FINAL,False,"broker rejected order without retry classification")
    code=rejection_code.strip().upper()
    retryable={"PRICE_CHANGED","REQUOTE","MARKET_BUSY"}
    if code in retryable:
        return BrokerOutcomeDecision(BrokerOutcome.REJECTED_RETRYABLE,True,f"explicit retryable broker rejection: {code}")
    return BrokerOutcomeDecision(BrokerOutcome.REJECTED_FINAL,False,f"final broker rejection: {code}")
