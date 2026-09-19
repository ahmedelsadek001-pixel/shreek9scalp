"""Explicit risk state machine for SHREEK V5.1."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


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

    def can_open(self) -> bool:
        return self.state is RiskState.ARMED

    def record_result(self, pnl: float) -> None:
        if pnl == 0:
            return
        if pnl < 0:
            self.consecutive_losses += 1
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

    def reset(self) -> None:
        self.consecutive_losses = 0
        self.state = RiskState.ARMED
