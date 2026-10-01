"""Explicit risk state machine for SHREEK V5.1."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite


class RiskState(str, Enum):
    ARMED = "ARMED"
    COOLDOWN = "COOLDOWN"
    KILLED = "KILLED"


@dataclass
class RiskStateMachine:
    state: RiskState = RiskState.ARMED
    consecutive_losses: int = 0
    max_consecutive_losses: int = 3

    def __post_init__(self) -> None:
        if not isinstance(self.state, RiskState):
            raise ValueError("state must be a RiskState")
        if (isinstance(self.max_consecutive_losses, bool)
                or not isinstance(self.max_consecutive_losses, int)
                or self.max_consecutive_losses <= 0):
            raise ValueError("max_consecutive_losses must be a positive integer")
        if (isinstance(self.consecutive_losses, bool)
                or not isinstance(self.consecutive_losses, int)
                or self.consecutive_losses < 0):
            raise ValueError("consecutive_losses must be a non-negative integer")
        if self.consecutive_losses > self.max_consecutive_losses:
            raise ValueError("consecutive_losses cannot exceed max_consecutive_losses")

    def can_open(self) -> bool:
        return self.state is RiskState.ARMED

    def record_result(self, pnl: float) -> None:
        """Record a finite numeric result without accepting bool or coercions."""
        if isinstance(pnl, bool) or not isinstance(pnl, (int, float)):
            raise ValueError("pnl must be a finite number")
        try:
            normalized_pnl = float(pnl)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("pnl must be a finite number") from exc
        if not isfinite(normalized_pnl):
            raise ValueError("pnl must be a finite number")
        if normalized_pnl == 0:
            return
        if normalized_pnl < 0:
            # Saturate at the kill threshold; the counter carries no useful
            # additional information beyond that point and stays bounded.
            self.consecutive_losses = min(
                self.consecutive_losses + 1, self.max_consecutive_losses
            )
            self.state = (
                RiskState.KILLED
                if self.consecutive_losses >= self.max_consecutive_losses
                else RiskState.COOLDOWN
            )
        else:
            self.consecutive_losses = 0
            if self.state is not RiskState.KILLED:
                self.state = RiskState.ARMED

    def arm(self) -> None:
        if self.state is RiskState.KILLED:
            raise RuntimeError("killed risk state requires explicit reset")
        self.state = RiskState.ARMED

    def kill(self) -> None:
        self.state = RiskState.KILLED

    def reset(self, *, operator_approved: bool = False, reason: str = "") -> None:
        """Reset only after explicit, auditable operator approval.

        A killed risk state is a safety boundary, not a cooldown timer. The
        default therefore fails closed; a caller must provide an explicit
        boolean approval and a non-empty reason before re-arming the machine.
        This method has no broker or live-execution authority.
        """
        if type(operator_approved) is not bool or not operator_approved:
            raise RuntimeError("risk reset requires explicit operator approval")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("risk reset requires a non-empty reason")
        self.consecutive_losses = 0
        self.state = RiskState.ARMED
