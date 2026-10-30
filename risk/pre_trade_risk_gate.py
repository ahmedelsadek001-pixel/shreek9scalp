"""Unified risk admission for SHREEK V5.1.

This layer validates risk state and daily loss capacity. It does not execute orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import isfinite

from risk.daily_risk_ledger import DailyRiskLedger
from risk.risk_state import RiskState, RiskStateMachine


@dataclass(frozen=True)
class RiskAdmission:
    allowed: bool
    reason: str
    modeled_loss: float
    remaining_loss: float


def evaluate_risk(
    day: date,
    modeled_loss: float,
    ledger: DailyRiskLedger,
    state: RiskStateMachine,
) -> RiskAdmission:
    """Fail closed unless the state and daily loss budget both permit a trade."""
    if not isinstance(day, date):
        raise TypeError("day must be a date")

    try:
        normalized_loss = float(modeled_loss)
    except (TypeError, ValueError, OverflowError):
        return RiskAdmission(False, "invalid modeled loss", 0.0, ledger.loss_remaining(day))

    if not isfinite(normalized_loss) or normalized_loss < 0:
        return RiskAdmission(False, "invalid modeled loss", normalized_loss, ledger.loss_remaining(day))

    remaining = ledger.loss_remaining(day)
    if state.state is not RiskState.ARMED:
        return RiskAdmission(False, f"risk state is {state.state.value}", normalized_loss, remaining)
    if not ledger.can_open(day, normalized_loss):
        return RiskAdmission(False, "daily risk budget exhausted", normalized_loss, remaining)
    return RiskAdmission(True, "risk admission passed", normalized_loss, remaining)
