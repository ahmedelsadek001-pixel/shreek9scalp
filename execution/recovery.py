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
        self._shadow = shadow
        self._state = RecoveryState.CONNECTED

    @property
    def shadow(self) -> ShadowExecution:
        return self._shadow

    @property
    def state(self) -> RecoveryState:
        return self._state

    def _pending_order_ids(self) -> tuple[str, ...] | None:
        """Return validated pending identities, or None when shadow state is untrustworthy."""
        try:
            pending = self._shadow.pending_order_ids()
        except Exception:
            return None
        if not isinstance(pending, tuple):
            return None
        if any(type(order_id) is not str or not order_id.strip() for order_id in pending):
            return None
        if len(pending) != len(set(pending)):
            return None
        return tuple(sorted(pending))

    def disconnect(self) -> RecoveryDecision:
        self._state = RecoveryState.DISCONNECTED
        return RecoveryDecision(self._state, False, "execution channel disconnected")

    def begin_recovery(self) -> RecoveryDecision:
        if self._state is not RecoveryState.DISCONNECTED:
            return RecoveryDecision(self._state, False, "recovery requires disconnected state")
        self._state = RecoveryState.RECOVERING
        return RecoveryDecision(self._state, False, "recovery in progress")

    def complete_recovery(self) -> RecoveryDecision:
        if self._state is not RecoveryState.RECOVERING:
            return RecoveryDecision(self._state, False, "recovery is not in progress")
        pending = self._pending_order_ids()
        if pending is None:
            return RecoveryDecision(self._state, False, "shadow recovery state unavailable")
        if pending:
            return RecoveryDecision(self._state, False, "pending shadow orders require reconciliation")
        self._state = RecoveryState.CONNECTED
        return RecoveryDecision(self._state, True, "execution channel recovered")

    def admission(self) -> RecoveryDecision:
        if self._state is not RecoveryState.CONNECTED:
            return RecoveryDecision(self._state, False, "execution channel is not ready")
        pending = self._pending_order_ids()
        if pending is None:
            return RecoveryDecision(self._state, False, "shadow recovery state unavailable")
        if pending:
            return RecoveryDecision(self._state, False, "pending shadow orders require reconciliation")
        return RecoveryDecision(self._state, True, "execution channel available")
