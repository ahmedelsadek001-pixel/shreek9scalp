"""Fail-closed shadow execution recovery state for SHREEK V5.1."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from execution.shadow import ShadowExecution


class RecoveryState(Enum):
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    RECOVERING = "RECOVERING"


@dataclass(frozen=True)
class RecoveryDecision:
    state: RecoveryState
    can_submit: bool
    reason: str


class ShadowRecovery:
    """Connection state machine that blocks submissions until recovery is safe."""

    def __init__(self, shadow: ShadowExecution) -> None:
        if not isinstance(shadow, ShadowExecution):
            raise TypeError("shadow must be ShadowExecution")
        self.shadow = shadow
        self.state = RecoveryState.CONNECTED

    def disconnect(self) -> RecoveryDecision:
        self.state = RecoveryState.DISCONNECTED
        return RecoveryDecision(self.state, False, "execution channel disconnected")

    def begin_recovery(self) -> RecoveryDecision:
        if self.state is not RecoveryState.DISCONNECTED:
            return RecoveryDecision(self.state, False, "recovery requires disconnected state")
        self.state = RecoveryState.RECOVERING
        return RecoveryDecision(self.state, False, "recovery in progress")

    def complete_recovery(self) -> RecoveryDecision:
        if self.state is not RecoveryState.RECOVERING:
            return RecoveryDecision(self.state, False, "recovery is not in progress")
        pending = self.shadow.pending_order_ids()
        if pending:
            return RecoveryDecision(self.state, False, "pending shadow orders require reconciliation")
        self.state = RecoveryState.CONNECTED
        return RecoveryDecision(self.state, True, "execution channel recovered")

    def admission(self) -> RecoveryDecision:
        if self.state is not RecoveryState.CONNECTED:
            return RecoveryDecision(self.state, False, "execution channel is not ready")
        pending = self.shadow.pending_order_ids()
        if pending:
            return RecoveryDecision(self.state, False, "pending shadow orders require reconciliation")
        return RecoveryDecision(self.state, True, "execution channel available")
